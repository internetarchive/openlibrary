import logging
import re
from collections.abc import Callable
from typing import Any

from openlibrary.catalog.marc.get_subjects import subjects_for_work
from openlibrary.catalog.marc.marc_base import (
    BadMARC,
    MarcBase,
    MarcException,
    MarcFieldBase,
    NoTitle,
)
from openlibrary.catalog.utils import (
    pick_first_date,
    remove_trailing_dot,
    remove_trailing_number_dot,
    tidy_isbn,
)

DNB_AGENCY_CODE = 'DE-101'
logger = logging.getLogger('openlibrary.catalog.marc')
max_number_of_pages = 50000  # no monograph should be longer than 50,000 pages
re_bad_char = re.compile('\ufffd')
re_date = re.compile(r'^[0-9]+u*$')
re_question = re.compile(r'^\?+$')
re_lccn = re.compile(r'([ \dA-Za-z\-]{3}[\d/-]+).*')
re_oclc = re.compile(r'^\(OCoLC\).*?0*(\d+)')
re_ocolc = re.compile('^ocolc *$', re.I)
re_ocn_or_ocm = re.compile(r'^oc[nm]0*(\d+) *$')
re_int = re.compile(r'\d{2,}')
re_bracket_field = re.compile(r'^\s*(\[.*\])\.?\s*$')


def strip_foc(s: str) -> str:
    foc = '[from old catalog]'
    return s[: -len(foc)].rstrip() if s.endswith(foc) else s


class SeeAlsoAsTitle(MarcException):
    pass


# FIXME: This is SUPER hard to find when needing to add a new field. Why not just decode everything?
FIELDS_WANTED = (
    [
        '001',
        '003',  # for OCLC
        '008',  # publish date, country and language
        '010',  # lccn
        '016',  # National Bibliographic Agency Control Number (for DNB)
        '020',  # isbn
        '022',  # issn
        '035',  # oclc
        '041',  # languages
        '050',  # lc classification
        '082',  # dewey
        '100',
        '110',
        '111',  # authors
        '130',
        '240',  # work title
        '245',  # title
        '250',  # edition
        '260',
        '264',  # publisher
        '300',  # pagination
        '440',
        '490',
        '830',  # series
    ]
    + [str(i) for i in range(500, 588)]
    + [  # notes + toc + description
        # 6XX subjects are extracted separately by get_subjects.subjects_for_work()
        '700',
        '710',
        '711',
        '720',  # contributions
        '246',
        '730',
        '740',  # other titles
        '852',  # location
        '856',  # electronic location / URL
    ]
)


def read_dnb(rec: MarcBase) -> dict[str, list[str]] | None:
    fields = rec.get_fields('016')
    for f in fields:
        (source,) = f.get_subfield_values('2') or ['']
        (control_number,) = f.get_subfield_values('a') or ['']
        if source == DNB_AGENCY_CODE and control_number:
            return {'dnb': [control_number]}
    return None


def read_issn(rec: MarcBase) -> dict[str, list[str]] | None:
    fields = rec.get_fields('022')
    if not fields:
        return None
    return {'issn': [v for f in fields for v in f.get_subfield_values('a')]}


def read_lccn(rec: MarcBase) -> list[str]:
    fields = rec.get_fields('010')
    found = []
    for f in fields:
        for lccn in f.get_subfield_values('a'):
            if re_question.match(lccn):
                continue
            m = re_lccn.search(lccn)
            if not m:
                continue
            lccn = m.group(1).strip()
            # zero-pad any dashes so the final digit group has size = 6
            lccn = lccn.replace('-', '0' * (7 - (len(lccn) - lccn.find('-'))))
            if lccn:
                found.append(lccn)
    return found


def remove_duplicates(seq: list[Any]) -> list[Any]:
    u = []
    for x in seq:
        if x not in u:
            u.append(x)
    return u


def read_oclc(rec: MarcBase) -> list[str]:
    found = []
    tag_001 = rec.get_control('001')
    tag_003 = rec.get_control('003')
    if tag_001 and tag_003 and re_ocolc.match(tag_003):
        oclc = tag_001
        m = re_ocn_or_ocm.match(oclc)
        if m:
            oclc = m.group(1)
        if oclc.isdigit():
            found.append(oclc)

    for f in rec.get_fields('035'):
        for v in f.get_subfield_values('a'):
            m = re_oclc.match(v)
            if not m:
                m = re_ocn_or_ocm.match(v)
                if m and not m.group(1).isdigit():
                    m = None
            if m:
                oclc = m.group(1)
                if oclc not in found:
                    found.append(oclc)
    return remove_duplicates(found)


def read_lc_classification(rec: MarcBase) -> list[str]:
    fields = rec.get_fields('050')
    found = []
    for f in fields:
        contents = f.get_contents('ab')
        if 'b' in contents:
            b = ' '.join(contents['b'])
            if 'a' in contents:
                found += [f'{a} {b}' for a in contents['a']]
            else:
                found += [b]
        # https://openlibrary.org/show-marc/marc_university_of_toronto/uoft.marc:671135731:596
        elif 'a' in contents:
            found += contents['a']
    return found


def read_isbn(rec: MarcBase) -> dict[str, str] | None:
    fields = rec.get_fields('020')
    if not fields:
        return None
    found = [isbn for f in fields for isbn in tidy_isbn(rec.read_isbn(f))]
    isbns: dict[str, Any] = {'isbn_10': [], 'isbn_13': []}
    for isbn in remove_duplicates(found):
        if len(isbn) == 13:
            isbns['isbn_13'].append(isbn)
        elif len(isbn) <= 16:
            isbns['isbn_10'].append(isbn)
    return {k: v for k, v in isbns.items() if v}


def read_dewey(rec: MarcBase) -> list[str]:
    fields = rec.get_fields('082')
    return [v for f in fields for v in f.get_subfield_values('a')]


def read_work_titles(rec: MarcBase) -> list[str]:
    found = []
    if tag_240 := rec.get_fields('240'):
        for f in tag_240:
            parts = f.get_subfield_values('amnpr')
            found.append(remove_trailing_dot(' '.join(parts).strip(',')))
    if tag_130 := rec.get_fields('130'):
        for f in tag_130:
            title = title_from_list(
                [v for k, v in f.get_all_subfields() if k.islower() and k != 'n']
            )
            found.append(title)
    return remove_duplicates(found)


def title_from_list(title_parts: list[str], delim: str = ' ') -> str:
    # For cataloging punctuation complexities, see https://www.oclc.org/bibformats/en/onlinecataloging.html#punctuation
    STRIP_CHARS = r' /,;:='  # Typical trailing punctuation for 245 subfields in ISBD cataloging standards
    return delim.join(remove_trailing_dot(s.strip(STRIP_CHARS)) for s in title_parts)


def read_title(rec: MarcBase) -> dict[str, Any]:
    fields = rec.get_fields('245') or rec.get_fields('740')
    if not fields:
        raise NoTitle('No Title found in either 245 or 740 fields.')
    # example MARC record with multiple titles:
    # https://openlibrary.org/show-marc/marc_western_washington_univ/wwu_bibs.mrc_revrev.mrc:299505697:862
    contents = fields[0].get_contents('ach')
    linkages = fields[0].get_contents('6')
    bnps = fields[0].get_subfield_values('bnps')
    ret: dict[str, Any] = {}
    title = alternate = None
    if '6' in linkages:
        alternate = rec.get_linkage('245', linkages['6'][0])
    # MARC record with 245$a missing:
    # https://openlibrary.org/show-marc/marc_western_washington_univ/wwu_bibs.mrc_revrev.mrc:516779055:1304
    if 'a' in contents:
        title = title_from_list(contents['a'])
    elif bnps:
        title = title_from_list([bnps.pop(0)])
    # talis_openlibrary_contribution/talis-openlibrary-contribution.mrc:183427199:255
    if title in ('See', 'See also'):
        raise SeeAlsoAsTitle(f'Title is: {title}')
    # talis_openlibrary_contribution/talis-openlibrary-contribution.mrc:5654086:483
    if not title:
        subfields = fields[0].get_lower_subfield_values()
        title = title_from_list(list(subfields))
        if not title:  # ia:scrapbooksofmoun03tupp
            raise NoTitle('No title found from joining subfields.')
    if alternate:
        ret['title'] = title_from_list(list(alternate.get_subfield_values('a')))
        ret['other_titles'] = [title]
    else:
        ret['title'] = title

    # Subtitle
    if bnps:
        ret['subtitle'] = title_from_list(bnps, delim=' : ')
    elif alternate:
        subtitle = alternate.get_subfield_values('bnps')
        if subtitle:
            ret['subtitle'] = title_from_list(subtitle, delim=' : ')
    if 'subtitle' in ret and re_bracket_field.match(ret['subtitle']):
        # Remove entirely bracketed subtitles
        ret.pop('subtitle')

    # By statement
    if 'c' in contents:
        ret['by_statement'] = remove_trailing_dot(' '.join(contents['c']))
    # Physical format
    if 'h' in contents:
        h = ' '.join(contents['h']).strip(' ')
        m = re_bracket_field.match(h)
        if m:
            h = m.group(1)
        assert h
        ret['physical_format'] = h
    return ret


def read_edition_name(rec: MarcBase) -> str:
    fields = rec.get_fields('250')
    found = [v for f in fields for v in f.get_lower_subfield_values()]
    return ' '.join(found).strip('[]')


lang_map = {
    'ser': 'srp',  # https://www.archive.org/details/zadovoljstvauivo00lubb
    'end': 'eng',
    'enk': 'eng',
    'ent': 'eng',
    'jap': 'jpn',
    'fra': 'fre',
    'fle': 'dut',  # Flemish -> Dutch
    # 2 character to 3 character codes
    'fr ': 'fre',
    'it ': 'ita',
    # LOC MARC Deprecated code updates
    # Only covers deprecated codes where there
    # is a direct 1-to-1 mapping to a single new code.
    'cam': 'khm',  # Khmer
    'esp': 'epo',  # Esperanto
    'eth': 'gez',  # Ethiopic
    'far': 'fao',  # Faroese
    'fri': 'fry',  # Frisian
    'gae': 'gla',  # Scottish Gaelic
    'gag': 'glg',  # Galician
    'gal': 'orm',  # Oromo
    'gua': 'grn',  # Guarani
    'int': 'ina',  # Interlingua (International Auxiliary Language Association)
    'iri': 'gle',  # Irish
    'lan': 'oci',  # Occitan (post 1500)
    'lap': 'smi',  # Sami
    'mla': 'mlg',  # Malagasy
    'mol': 'rum',  # Romanian
    'sao': 'smo',  # Samoan
    'scc': 'srp',  # Serbian
    'scr': 'hrv',  # Croatian
    'sho': 'sna',  # Shona
    'snh': 'sin',  # Sinhalese
    'sso': 'sot',  # Sotho
    'swz': 'ssw',  # Swazi
    'tag': 'tgl',  # Tagalog
    'taj': 'tgk',  # Tajik
    'tar': 'tat',  # Tatar
    'tsw': 'tsn',  # Tswana
}


def read_original_languages(rec: MarcBase) -> list[str]:
    found = []
    fields = rec.get_fields('041')
    for f in fields:
        is_translation = f.ind1() == '1'
        found += [v.lower() for v in f.get_subfield_values('h') if len(v) == 3]
    return [lang_map.get(v, v) for v in found if v != 'zxx']


def read_languages(rec: MarcBase, lang_008: str | None = None) -> list[str]:
    """Read languages from 041, if present, and combine with language from 008:35-37"""
    found = []
    if lang_008:
        lang_008 = lang_008.lower()
        if lang_008 not in ('   ', '###', '|||', '', '???', 'zxx', 'n/a'):
            found.append(lang_008)

    for f in rec.get_fields('041'):
        if f.ind2() == '7':
            code_source = ' '.join(f.get_subfield_values('2'))
            logger.error(f'Unrecognised language source = {code_source}')
            continue  # Skip anything which is using a non-MARC code source e.g. iso639-1
        for value in f.get_subfield_values('a'):
            value = value.replace(' ', '').replace('-', '')  # remove pad/separators
            if len(value) % 3 == 0:
                # Obsolete cataloging practice was to concatenate all language codes in a single subfield
                for k in range(0, len(value), 3):
                    code = value[k : k + 3].lower()
                    if code != 'zxx' and code not in found:
                        found.append(code)
            else:
                logger.error(f'Unrecognised MARC language code(s) = {value}')
    return [lang_map.get(code, code) for code in found]


def read_pub_date(rec: MarcBase) -> str | None:
    """
    Read publish date from 260$c.
    """

    def publish_date(s: str) -> str:
        date = s.strip('[]')
        if date.lower() in ('n.d.', 's.d.'):  # No date
            date = '[n.d.]'
        return remove_trailing_number_dot(date)

    found = [v for f in rec.get_fields('260') for v in f.get_subfield_values('c')]
    return publish_date(found[0]) if found else None


def read_publisher(rec: MarcBase) -> dict[str, Any] | None:
    def publisher_name(s: str) -> str:
        name = s.strip(' /,;:[]')
        if name.lower().startswith('s.n'):  # Sine nomine
            name = '[s.n.]'
        return name

    def publish_place(s: str) -> str:
        place = s.strip(' /.,;:')
        # remove encompassing []
        if (place[0], place[-1]) == ('[', ']'):
            place = place[1:-1]
        # clear unbalanced []
        if place.count('[') != place.count(']'):
            place = place.strip('[]')
        if place.lower().startswith('s.l'):  # Sine loco
            place = '[s.l.]'
        return place

    fields = (
        rec.get_fields('260')
        or rec.get_fields('264')[:1]
        or [link for link in [rec.get_linkage('260', '880')] if link]
    )
    if not fields:
        return None
    publisher = []
    publish_places = []
    for f in fields:
        contents = f.get_contents('ab')
        if 'b' in contents:
            publisher += [publisher_name(v) for v in contents['b']]
        if 'a' in contents:
            publish_places += [publish_place(v) for v in contents['a']]
    edition = {}
    if publisher:
        edition['publishers'] = publisher
    if len(publish_places) and publish_places[0]:
        edition['publish_places'] = publish_places
    return edition


def name_from_list(name_parts: list[str], strip_trailing_dot: bool = True) -> str:
    STRIP_CHARS = r' /,;:[]'
    name = ' '.join(strip_foc(s).strip(STRIP_CHARS) for s in name_parts)
    return remove_trailing_dot(name) if strip_trailing_dot else name


def read_author_person(field: MarcFieldBase, tag: str = '100') -> dict[str, Any]:
    """
    This take either a MARC 100 Main Entry - Personal Name (non-repeatable) field
      or
    700 Added Entry - Personal Name (repeatable)
      or
    720 Added Entry - Uncontrolled Name (repeatable)
    and returns an author import dict.
    """
    author: dict[str, Any] = {}
    contents = field.get_contents('abcde6')
    if 'a' not in contents and 'c' not in contents:
        # Should have at least a name or title.
        return author
    if 'd' in contents:
        author = pick_first_date(strip_foc(d).strip(',[]') for d in contents['d'])
    author['name'] = name_from_list(field.get_subfield_values('abc'))
    author['entity_type'] = 'person'
    subfields = [
        ('a', 'personal_name'),
        ('b', 'numeration'),
        ('c', 'title'),
        ('e', 'role'),
    ]
    for subfield, field_name in subfields:
        if subfield in contents:
            strip_trailing_dot = field_name != 'role'
            author[field_name] = name_from_list(contents[subfield], strip_trailing_dot)
    if author['name'] == author.get('personal_name'):
        del author['personal_name']  # DRY names
    if 'q' in contents:
        author['fuller_name'] = ' '.join(contents['q'])
    if '6' in contents:  # noqa: SIM102 - alternate script name exists
        if (link := field.rec.get_linkage(tag, contents['6'][0])) and (
            name := link.get_subfield_values('a')
        ):
            author['alternate_names'] = [author['name']]
            author['name'] = name_from_list(name)
    return author


def person_last_name(field: MarcFieldBase) -> str:
    v = field.get_subfield_values('a')[0]
    return v[: v.find(', ')] if ', ' in v else v


def last_name_in_245c(rec: MarcBase, person: MarcFieldBase) -> bool:
    fields = rec.get_fields('245')
    last_name = person_last_name(person).lower()
    return any(
        any(last_name in v.lower() for v in f.get_subfield_values('c')) for f in fields
    )


def read_authors(rec: MarcBase) -> list[dict]:
    fields_person = rec.read_fields(['100', '700'])
    fields_org = rec.read_fields(['110', '710'])
    fields_event = rec.get_fields('111')
    if not any([fields_person, fields_org, fields_event]):
        return []
    seen_names: set[str] = set()
    found = []
    for a in (
        read_author_person(f, tag=tag)
        for tag, f in fields_person
        if isinstance(f, MarcFieldBase)
    ):
        name = a.get('name')
        if name and name not in seen_names:
            seen_names.add(name)
            found.append(a)
    for tag, f in fields_org:
        assert isinstance(f, MarcFieldBase)
        alt_name = ''
        if links := f.get_contents('6'):
            alt_name = name_from_list(f.get_subfield_values('ab'))
            f = f.rec.get_linkage(tag, links['6'][0]) or f
        name = name_from_list(f.get_subfield_values('ab'))
        author: dict[str, Any] = {'entity_type': 'org', 'name': name}
        if alt_name:
            author['alternate_names'] = [alt_name]
        found.append(author)
    for f in fields_event:
        assert isinstance(f, MarcFieldBase)
        name = name_from_list(f.get_subfield_values('acdn'))
        found.append({'entity_type': 'event', 'name': name})
    return found


def read_pagination(rec: MarcBase) -> dict[str, Any] | None:
    fields = rec.get_fields('300')
    if not fields:
        return None
    pagination = []
    edition: dict[str, Any] = {}
    for f in fields:
        pagination += f.get_subfield_values('a')
    if pagination:
        edition['pagination'] = ' '.join(pagination)
        # strip trailing characters from pagination
        edition['pagination'] = edition['pagination'].strip(' ,:;')
        num = []
        for x in pagination:
            num += [int(i) for i in re_int.findall(x.replace(',', ''))]
            num += [int(i) for i in re_int.findall(x)]
        valid = [i for i in num if i < max_number_of_pages]
        if valid:
            edition['number_of_pages'] = max(valid)
    return edition


def read_series(rec: MarcBase) -> list[str]:
    found = []
    for tag in ('440', '490', '830'):
        fields = rec.get_fields(tag)
        for f in fields:
            this = []
            for v in f.get_subfield_values('av'):
                if v := v.rstrip('.,; '):
                    this.append(v)
            if this:
                found.append(' -- '.join(this))
    return remove_duplicates(found)


def read_notes(rec: MarcBase) -> str:
    found = []
    for tag in range(500, 590):
        if tag in (505, 520):
            continue
        fields = rec.get_fields(str(tag))
        for f in fields:
            found.append(' '.join(f.get_lower_subfield_values()).strip())
    return '\n\n'.join(found)


def read_description(rec: MarcBase) -> str:
    fields = rec.get_fields('520')
    found = [v for f in fields for v in f.get_subfield_values('a')]
    return "\n\n".join(found)


def read_url(rec: MarcBase) -> list:
    found = []
    for f in rec.get_fields('856'):
        contents = f.get_contents('uy3zx')
        if not contents.get('u'):
            continue
        parts = (
            contents.get('y')
            or contents.get('3')
            or contents.get('z')
            or contents.get('x', ['External source'])
        )
        if parts:
            title = parts[0].strip()
            found += [{'url': u.strip(), 'title': title} for u in contents['u']]
    return found


def read_other_titles(rec: MarcBase):
    return (
        [' '.join(f.get_subfield_values('a')) for f in rec.get_fields('246')]
        + [' '.join(f.get_lower_subfield_values()) for f in rec.get_fields('730')]
        + [' '.join(f.get_subfield_values('apn')) for f in rec.get_fields('740')]
    )


def read_location(rec: MarcBase) -> list[str] | None:
    fields = rec.get_fields('852')
    found = [v for f in fields for v in f.get_subfield_values('a')]
    return remove_duplicates(found) if fields else None


def read_toc(rec: MarcBase) -> list:
    fields = rec.get_fields('505')
    toc = []
    for f in fields:
        toc_line: list[str] = []
        for k, v in f.get_all_subfields():
            if k == 'a':
                toc_split = [i.strip() for i in v.split('--')]
                if any(len(i) > 2048 for i in toc_split):
                    toc_split = [i.strip() for i in v.split(' - ')]
                # http://openlibrary.org/show-marc/marc_miami_univ_ohio/allbibs0036.out:3918815:7321
                if any(len(i) > 2048 for i in toc_split):
                    toc_split = [i.strip() for i in v.split('; ')]
                # FIXME:
                # http://openlibrary.org/show-marc/marc_western_washington_univ/wwu_bibs.mrc_revrev.mrc:938969487:3862
                if any(len(i) > 2048 for i in toc_split):
                    toc_split = [i.strip() for i in v.split(' / ')]
                assert isinstance(toc_split, list)
                toc.extend(toc_split)
                continue
            if k == 't':
                if toc_line:
                    toc.append(' -- '.join(toc_line))
                if len(v) > 2048:
                    toc_line = [i.strip() for i in v.strip('/').split('--')]
                else:
                    toc_line = [v.strip('/')]
                continue
            if k.islower():  # Exclude numeric, non-display subfields like $6, $7, $8
                toc_line.append(v.strip(' -'))
        if toc_line:
            toc.append('-- '.join(toc_line))
    return [{'title': s, 'type': '/type/toc_item'} for s in toc]


def update_edition(
    rec: MarcBase, edition: dict[str, Any], func: Callable, field: str
) -> None:
    if v := func(rec):
        if field in edition and isinstance(edition[field], list):
            edition[field] += v
        else:
            edition[field] = v


def read_edition(rec: MarcBase) -> dict[str, Any]:
    """
    Converts MARC record object into a dict representation of an edition
    suitable for importing into Open Library.

    :param (MarcBinary | MarcXml) rec:
    :rtype: dict
    :return: Edition representation
    """
    handle_missing_008 = True
    edition: dict[str, Any] = {}
    if tag_008 := rec.get_control('008'):
        f = re_bad_char.sub(' ', tag_008)
        if not f:
            raise BadMARC("'008' field must not be blank")
        publish_date = f[7:11]

        if re_date.match(publish_date) and publish_date not in ('0000', '9999'):
            edition['publish_date'] = publish_date
        if f[6] == 'r' and f[11:15] > publish_date:
            # Incorrect reprint date order
            update_edition(rec, edition, read_pub_date, 'publish_date')
        elif f[6] == 't':  # Copyright date
            edition['copyright_date'] = f[11:15]
        if 'publish_date' not in edition:  # Publication date fallback to 260$c
            update_edition(rec, edition, read_pub_date, 'publish_date')
        publish_country = f[15:18]
        if publish_country not in ('|||', '   ', '\x01\x01\x01', '???'):
            edition['publish_country'] = publish_country.strip()
        if languages := read_languages(rec, lang_008=f[35:38].lower()):
            edition['languages'] = languages
    elif handle_missing_008:
        update_edition(rec, edition, read_languages, 'languages')
        update_edition(rec, edition, read_pub_date, 'publish_date')
    else:
        raise BadMARC("single '008' field required")

    update_edition(rec, edition, read_work_titles, 'work_titles')
    try:
        edition.update(read_title(rec))
    except NoTitle:
        if 'work_titles' in edition:
            assert len(edition['work_titles']) == 1
            edition['title'] = edition['work_titles'][0]
            del edition['work_titles']
        else:
            raise

    update_edition(rec, edition, read_lccn, 'lccn')
    update_edition(rec, edition, read_dnb, 'identifiers')
    update_edition(rec, edition, read_issn, 'identifiers')
    update_edition(rec, edition, read_authors, 'authors')
    update_edition(rec, edition, read_oclc, 'oclc_numbers')
    update_edition(rec, edition, read_lc_classification, 'lc_classifications')
    update_edition(rec, edition, read_dewey, 'dewey_decimal_class')
    update_edition(rec, edition, read_other_titles, 'other_titles')
    update_edition(rec, edition, read_edition_name, 'edition_name')
    update_edition(rec, edition, read_series, 'series')
    update_edition(rec, edition, read_notes, 'notes')
    update_edition(rec, edition, read_description, 'description')
    update_edition(rec, edition, read_location, 'location')
    update_edition(rec, edition, read_toc, 'table_of_contents')
    update_edition(rec, edition, read_url, 'links')
    update_edition(rec, edition, read_original_languages, 'translated_from')

    edition.update(subjects_for_work(rec))

    for func in (read_publisher, read_isbn, read_pagination):
        v = func(rec)
        if v:
            edition.update(v)
    return edition
