""" This entire module is deprecated,
    openlibrary.catalog.marc.get_subjects is the preferred module
"""

# Tell the flake8 linter to ignore this deprecated file.
# flake8: noqa

from collections import defaultdict
from deprecated import deprecated
from lxml import etree
import re


from openlibrary.catalog.importer.db_read import get_mc
from openlibrary.catalog.get_ia import get_from_archive, marc_formats, urlopen_keep_trying
from openlibrary.catalog.marc import get_subjects
from openlibrary.catalog.marc.marc_binary import MarcBinary
from openlibrary.catalog.marc.marc_xml import read_marc_file, MarcXml, BlankTag, BadSubtag
from openlibrary.catalog.utils import remove_trailing_dot, remove_trailing_number_dot, flip_name


subject_fields = set(['600', '610', '611', '630', '648', '650', '651', '662'])

re_flip_name = re.compile('^(.+), ([A-Z].+)$')

# 'Rhodes, Dan (Fictitious character)'
re_fictitious_character = re.compile(r'^(.+), (.+)( \(.* character\))$')
re_etc = re.compile('^(.+?)[, .]+etc[, .]?$', re.I)
re_comma = re.compile('^([A-Z])([A-Za-z ]+?) *, ([A-Z][A-Z a-z]+)$')

re_place_comma = re.compile('^(.+), (.+)$')
re_paren = re.compile('[()]')


@deprecated('Use openlibrary.catalog.marc.get_subjects.flip_place() instead.')
def flip_place(s):
    return get_subjects.flip_place(s)


@deprecated('Use openlibrary.catalog.marc.get_subjects.flip_subject() instead.')
def flip_subject(s):
    return get_subjects.flip_subject(s)


@deprecated('Use openlibrary.catalog.marc.get_subjects.four_types() instead.')
def four_types(i):
    return get_subjects.four_types(i)


archive_url = "http://archive.org/download/"


@deprecated
def load_binary(ia):
    url = archive_url + ia + '/' + ia + '_meta.mrc'
    f = urlopen_keep_trying(url)
    data = f.read()
    assert '<title>Internet Archive: Page Not Found</title>' not in data[:200]
    if len(data) != int(data[:5]):
        data = data.decode('utf-8').encode('raw_unicode_escape')
    if len(data) != int(data[:5]):
        return
    return MarcBinary(data)


@deprecated
def load_xml(ia):
    url = archive_url + ia + '/' + ia + '_marc.xml'
    f = urlopen_keep_trying(url)
    root = etree.parse(f).getroot()
    if root.tag == '{http://www.loc.gov/MARC21/slim}collection':
        root = root[0]
    return MarcXml(root)


@deprecated
def subjects_for_work(rec):
    field_map = {
        'subject': 'subjects',
        'place': 'subject_places',
        'time': 'subject_times',
        'person': 'subject_people',
    }

    subjects = four_types(read_subjects(rec))

    return dict((field_map[k], list(v)) for k, v in subjects.items())

re_edition_key = re.compile(r'^/(?:b|books)/(OL\d+M)$')


@deprecated
def get_subjects_from_ia(ia):
    formats = marc_formats(ia)
    if not any(formats.values()):
        return {}
    rec = None
    if formats['bin']:
        rec = load_binary(ia)
    if not rec:
        assert formats['xml']
        rec = load_xml(ia)
    return read_subjects(rec)


re_ia_marc = re.compile(r'^(?:.*/)?([^/]+)_(marc\.xml|meta\.mrc)(:0:\d+)?$')
@deprecated
def get_work_subjects(w, do_get_mc=True):
    found = set()
    for e in w['editions']:
        sr = e.get('source_records', [])
        if sr:
            for i in sr:
                if i.endswith('initial import'):
                    continue
                if i.startswith('ia:') or i.startswith('marc:'):
                    found.add(i)
                    continue
        else:
            mc = None
            if do_get_mc:
                m = re_edition_key.match(e['key'])
                mc = get_mc('/b/' + m.group(1))
            if mc:
                if mc.endswith('initial import'):
                    continue
                if not mc.startswith('amazon:') and not re_ia_marc.match(mc):
                    found.add('marc:' + mc)
    subjects = []
    for sr in found:
        if sr.startswith('marc:ia:'):
            subjects.append(get_subjects_from_ia(sr[8:]))
        elif sr.startswith('marc:'):
            loc = sr[5:]
            data = get_from_archive(loc)
            rec = MarcBinary(data)
            subjects.append(read_subjects(rec))
        else:
            assert sr.startswith('ia:')
            subjects.append(get_subjects_from_ia(sr[3:]))
    return combine_subjects(subjects)


@deprecated('Use openlibrary.catalog.marc.get_subjects.tidy_subject() instead.')
def tidy_subject(s):
    return get_subjects.tidy_subject(s)


re_aspects = re.compile(' [Aa]spects$')


@deprecated
def find_aspects(f):
    cur = [(i, j) for i, j in f.get_subfields('ax')]
    if len(cur) < 2 or cur[0][0] != 'a' or cur[1][0] != 'x':
        return
    a, x = cur[0][1], cur[1][1]
    x = x.strip('. ')
    a = a.strip('. ')
    if not re_aspects.search(x):
        return
    if a == 'Body, Human':
        a = 'the Human body'
    return x + ' of ' + flip_subject(a)


@deprecated('Use openlibrary.catalog.marc.get_subjects.read_subject() instead.')
def read_subjects(rec):
    return get_subjects.read_subject(s)


@deprecated
def combine_subjects(subjects):
    all_subjects = defaultdict(lambda: defaultdict(int))
    for a in subjects:
        for b, c in a.items():
            for d, e in c.items():
                all_subjects[b][d] += e
    return dict((k, dict(v)) for k, v in all_subjects.items())
