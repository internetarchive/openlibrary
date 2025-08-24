import datetime
import re
from collections.abc import Iterable
from typing import TYPE_CHECKING
from unicodedata import normalize

import web

from openlibrary.plugins.upstream.utils import (
    LanguageMultipleMatchError,
    LanguageNoMatchError,
    convert_iso_to_marc,
    get_abbrev_from_full_lang_name,
    get_languages,
)
from openlibrary.utils import uniq

if TYPE_CHECKING:
    from openlibrary.catalog.add_book.load_book import AuthorImportDict
    from openlibrary.plugins.upstream.models import Author


EARLIEST_PUBLISH_YEAR_FOR_BOOKSELLERS = 1400
BOOKSELLERS_WITH_ADDITIONAL_VALIDATION = ['amazon', 'bwb']


def cmp(x, y):
    return (x > y) - (x < y)


re_date = map(
    re.compile,  # type: ignore[arg-type]
    [
        r'(?P<birth_date>\d+\??)-(?P<death_date>\d+\??)',
        r'(?P<birth_date>\d+\??)-',
        r'b\.? (?P<birth_date>(?:ca\. )?\d+\??)',
        r'd\.? (?P<death_date>(?:ca\. )?\d+\??)',
        r'(?P<birth_date>.*\d+.*)-(?P<death_date>.*\d+.*)',
        r'^(?P<birth_date>[^-]*\d+[^-]+ cent\.[^-]*)$',
    ],
)

re_ad_bc = re.compile(r'\b(B\.C\.?|A\.D\.?)')
re_date_fl = re.compile('^fl[., ]')
re_number_dot = re.compile(r'\d{2,}[- ]*(\.+)$')
re_l_in_date = re.compile(r'(l\d|\dl)')
re_end_dot = re.compile(r'[^ .][^ .]\.$', re.UNICODE)
re_marc_name = re.compile('^(.*?),+ (.*)$')
re_year = re.compile(r'\b(\d{4})\b')


def key_int(rec):
    # extract the number from a key like /a/OL1234A
    return int(web.numify(rec['key']))


def author_dates_match(a: "AuthorImportDict", b: "dict | Author") -> bool:
    """
    Checks if the years of two authors match. Only compares years,
    not names or keys. Works by returning False if any year specified in one record
    does not match that in the other, otherwise True. If any one author does not have
    dates, it will return True.

    :param dict a: Author import dict {"name": "Some One", "birth_date": "1960"}
    :param dict b: Author import dict {"name": "Some One"}
    """
    for k in ('birth_date', 'death_date', 'date'):
        if k not in a or a[k] is None or k not in b or b[k] is None:
            continue
        if a[k] == b[k] or a[k].startswith(b[k]) or b[k].startswith(a[k]):
            continue
        m1 = re_year.search(a[k])
        if not m1:
            return False
        m2 = re_year.search(b[k])
        if m2 and m1.group(1) == m2.group(1):
            continue
        return False
    return True


def flip_name(name: str) -> str:
    """
    Flip author name about the comma, stripping the comma, and removing non
    abbreviated end dots. Returns name with end dot stripped if no comma+space found.
    The intent is to convert a Library indexed name to natural name order.

    :param str name: e.g. "Smith, John." or "Smith, J."
    :return: e.g. "John Smith" or "J. Smith"
    """
    m = re_end_dot.search(name)
    if m:
        name = name[:-1]
    if name.find(', ') == -1:
        return name
    if m := re_marc_name.match(name):
        return m.group(2) + ' ' + m.group(1)
    return ''


def remove_trailing_number_dot(date):
    if m := re_number_dot.search(date):
        return date[: -len(m.group(1))]
    else:
        return date


def remove_trailing_dot(s):
    if s.endswith(' Dept.'):
        return s
    elif re_end_dot.search(s):
        return s[:-1]
    return s


def fix_l_in_date(date):
    if 'l' not in date:
        return date
    return re_l_in_date.sub(lambda m: m.group(1).replace('l', '1'), date)


re_ca = re.compile(r'ca\.([^ ])')


def parse_date(date):
    if re_date_fl.match(date):
        return {}
    date = remove_trailing_number_dot(date)
    date = re_ca.sub(lambda m: 'ca. ' + m.group(1), date)
    if date.find('-') == -1:
        for r in re_date:
            m = r.search(date)
            if m:
                return {k: fix_l_in_date(v) for k, v in m.groupdict().items()}
        return {}

    parts = date.split('-')
    i = {'birth_date': parts[0].strip()}
    if len(parts) == 2:
        parts[1] = parts[1].strip()
        if parts[1]:
            i['death_date'] = fix_l_in_date(parts[1])
            if not re_ad_bc.search(i['birth_date']):
                m = re_ad_bc.search(i['death_date'])
                if m:
                    i['birth_date'] += ' ' + m.group(1)
    if 'birth_date' in i and 'l' in i['birth_date']:
        i['birth_date'] = fix_l_in_date(i['birth_date'])
    return i


re_cent = re.compile(r'^[\dl][^-]+ cent\.$')


def pick_first_date(dates):
    # this is to handle this case:
    # 100: $aLogan, Olive (Logan), $cSikes, $dMrs., $d1839-
    # see http://archive.org/download/gettheebehindmes00logaiala/gettheebehindmes00logaiala_meta.mrc
    # or http://pharosdb.us.archive.org:9090/show-marc?record=gettheebehindmes00logaiala/gettheebehindmes00logaiala_meta.mrc:0:521

    dates = list(dates)
    if len(dates) == 1 and re_cent.match(dates[0]):
        return {'date': fix_l_in_date(dates[0])}

    for date in dates:
        result = parse_date(date)
        if result != {}:
            return result

    return {
        'date': fix_l_in_date(' '.join([remove_trailing_number_dot(d) for d in dates]))
    }


re_drop = re.compile('[?,]')


def match_with_bad_chars(a, b):
    if str(a) == str(b):
        return True
    a = normalize('NFKD', str(a)).lower()
    b = normalize('NFKD', str(b)).lower()
    if a == b:
        return True
    a = a.encode('ASCII', 'ignore')
    b = b.encode('ASCII', 'ignore')
    if a == b:
        return True

    def drop(s):
        return re_drop.sub('', s.decode() if isinstance(s, bytes) else s)

    return drop(a) == drop(b)


def accent_count(s):
    return len([c for c in norm(s) if ord(c) > 127])


def norm(s):
    return normalize('NFC', s) if isinstance(s, str) else s


def pick_best_name(names):
    names = [norm(n) for n in names]
    n1 = names[0]
    assert all(match_with_bad_chars(n1, n2) for n2 in names[1:])
    names.sort(key=lambda n: accent_count(n), reverse=True)
    assert '?' not in names[0]
    return names[0]


def pick_best_author(authors):
    n1 = authors[0]['name']
    assert all(match_with_bad_chars(n1, a['name']) for a in authors[1:])
    authors.sort(key=lambda a: accent_count(a['name']), reverse=True)
    assert '?' not in authors[0]['name']
    return authors[0]


def tidy_isbn(input):
    output = []
    for i in input:
        i = i.replace('-', '')
        if len(i) in (10, 13):
            output.append(i)
            continue
        if len(i) == 20 and all(c.isdigit() for c in i):
            output.extend([i[:10], i[10:]])
            continue
        if len(i) == 21 and not i[10].isdigit():
            output.extend([i[:10], i[11:]])
            continue
        if i.find(';') != -1:
            no_semicolon = i.replace(';', '')
            if len(no_semicolon) in (10, 13):
                output.append(no_semicolon)
                continue
            split = i.split(';')
            if all(len(j) in (10, 13) for j in split):
                output.extend(split)
                continue
        output.append(i)
    return output


def strip_count(counts):
    foo = {}
    for i, j in counts:
        foo.setdefault(i.rstrip('.').lower() if isinstance(i, str) else i, []).append(
            (i, j)
        )
    ret = {}
    for v in foo.values():
        m = max(v, key=lambda x: len(x[1]))[0]
        bar = []
        for i, j in v:
            bar.extend(j)
        ret[m] = bar
    return sorted(ret.items(), key=lambda x: len(x[1]), reverse=True)


def fmt_author(a):
    if 'birth_date' in a or 'death_date' in a:
        return "{} ({}-{})".format(
            a['name'], a.get('birth_date', ''), a.get('death_date', '')
        )
    return a['name']


def get_title(e):
    if e.get('title_prefix', None) is not None:
        prefix = e['title_prefix']
        if prefix[-1] != ' ':
            prefix += ' '
        title = prefix + e['title']
    else:
        title = e['title']
    return title


def get_publication_year(publish_date: str | int | None) -> int | None:
    """
    Return the publication year from a book in YYYY format by looking for four
    consecutive digits not followed by another digit. If no match, return None.

    >>> get_publication_year('1999-01')
    1999
    >>> get_publication_year('January 1, 1999')
    1999
    """
    if publish_date is None:
        return None
    match = re_year.search(str(publish_date))
    return int(match.group(0)) if match else None


def published_in_future_year(publish_year: int) -> bool:
    """
    Return True if a book is published in a future year as compared to the
    current year.

    Some import sources have publication dates in a future year, and the
    likelihood is high that this is bad data. So we don't want to import these.
    """
    return publish_year > datetime.datetime.now().year


def publication_too_old_and_not_exempt(rec: dict) -> bool:
    """
    Returns True for books that are 'too old' per
    EARLIEST_PUBLISH_YEAR_FOR_BOOKSELLERS, but that only applies to
    source records in BOOKSELLERS_WITH_ADDITIONAL_VALIDATION.

    For sources not in BOOKSELLERS_WITH_ADDITIONAL_VALIDATION, return False,
    as there is higher trust in their publication dates.
    """

    def source_requires_date_validation(rec: dict) -> bool:
        return any(
            record.split(":")[0] in BOOKSELLERS_WITH_ADDITIONAL_VALIDATION
            for record in rec.get('source_records', [])
        )

    if (
        publish_year := get_publication_year(rec.get('publish_date'))
    ) and source_requires_date_validation(rec):
        return publish_year < EARLIEST_PUBLISH_YEAR_FOR_BOOKSELLERS

    return False


def is_independently_published(publishers: list[str]) -> bool:
    """
    Return True if the book is independently published.

    """
    independent_publisher_names = [
        'independently published',
        'independent publisher',
        'createspace independent publishing platform',
    ]

    independent_publisher_names_casefolded = [
        name.casefold() for name in independent_publisher_names
    ]
    return any(
        publisher.casefold() in independent_publisher_names_casefolded
        for publisher in publishers
    )


def needs_isbn_and_lacks_one(rec: dict) -> bool:
    """
    Return True if the book is identified as requiring an ISBN.

    If an ISBN is NOT required, return False. If an ISBN is required:
        - return False if an ISBN is present (because the rec needs an ISBN and
          has one); or
        - return True if there's no ISBN.

    This exists because certain sources do not have great records and requiring
    an ISBN may help improve quality:
        https://docs.google.com/document/d/1dlN9klj27HeidWn3G9GUYwDNZ2F5ORoEZnG4L-7PcgA/edit#heading=h.1t78b24dg68q

    :param dict rec: an import dictionary record.
    """

    def needs_isbn(rec: dict) -> bool:
        # Exception for Amazon-specific ASINs, which often accompany ebooks
        if any(
            name == "amazon" and identifier.startswith("B")
            for record in rec.get("source_records", [])
            if record and ":" in record
            for name, identifier in [record.split(":", 1)]
        ):
            return False

        return any(
            record.split(":")[0] in BOOKSELLERS_WITH_ADDITIONAL_VALIDATION
            for record in rec.get('source_records', [])
        )

    def has_isbn(rec: dict) -> bool:
        return any(rec.get('isbn_10', []) or rec.get('isbn_13', []))

    return needs_isbn(rec) and not has_isbn(rec)


def is_promise_item(rec: dict) -> bool:
    """Returns True if the record is a promise item."""
    return any(
        record.startswith("promise:".lower())
        for record in rec.get('source_records', "")
    )


def get_non_isbn_asin(rec: dict) -> str | None:
    """
    Return a non-ISBN ASIN (e.g. B012345678) if one exists.

    There is a tacit assumption that at most one will exist.
    """
    # Look first in identifiers.
    amz_identifiers = rec.get("identifiers", {}).get("amazon", [])
    if asin := next(
        (identifier for identifier in amz_identifiers if identifier.startswith("B")),
        None,
    ):
        return asin

    # Finally, check source_records.
    if asin := next(
        (
            record.split(":")[-1]
            for record in rec.get("source_records", [])
            if record.startswith("amazon:B")
        ),
        None,
    ):
        return asin

    return None


def is_asin_only(rec: dict) -> bool:
    """Returns True if the rec has only an ASIN and no ISBN, and False otherwise."""
    # Immediately return False if any ISBNs are present
    if any(isbn_type in rec for isbn_type in ("isbn_10", "isbn_13")):
        return False

    # Check for Amazon source records starting with "B".
    if any(record.startswith("amazon:B") for record in rec.get("source_records", [])):
        return True

    # Check for Amazon identifiers starting with "B".
    amz_identifiers = rec.get("identifiers", {}).get("amazon", [])
    return any(identifier.startswith("B") for identifier in amz_identifiers)


def get_missing_fields(rec: dict) -> list[str]:
    """Return missing fields, if any."""
    required_fields = [
        'title',
        'source_records',
    ]
    return [field for field in required_fields if rec.get(field) is None]


class InvalidLanguage(Exception):
    def __init__(self, code):
        self.code = code

    def __str__(self):
        return f"invalid language code: '{self.code}'"


def format_languages(languages: Iterable) -> list[dict[str, str]]:
    """
    Map ImportRecord language data to match Open Library's expected format.

    Supports a variety of input formats, including:
    - Full key, e.g. /languages/eng
    - 3-letter code (MARC21), e.g. eng
    - Full name, e.g. English, Anglais
    - 2-letter code (ISO 639-1), e.g. en

    E.g. an input of ["English", "fre"], return:
    [{'key': '/languages/eng'}, {'key': '/languages/fre'}]
    """
    if not languages:
        return []

    lang_keys = []
    for language in languages:
        input_lang = language.lower()

        try:
            marc_lang_code = (
                # First check if it's a full key, eg /languages/eng
                get_languages().get(input_lang, {}).get('code')
                # Maybe it's a 3-letter code, eg eng
                or get_languages().get(f"/languages/{input_lang}", {}).get('code')
                # Check if it's a 2-letter code, eg en
                or convert_iso_to_marc(input_lang)
                # Check if it's a full name, eg English, Anglais, etc
                # Note this must be last, since it raises errors
                or get_abbrev_from_full_lang_name(language)
            )
        except (LanguageNoMatchError, LanguageMultipleMatchError):
            # get_abbrev_from_full_lang_name raises errors
            raise InvalidLanguage(input_lang)

        lang_keys.append(f'/languages/{marc_lang_code}')

    return [{'key': key} for key in uniq(lang_keys)]
