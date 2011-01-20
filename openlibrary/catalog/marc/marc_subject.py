from openlibrary.catalog.utils import remove_trailing_dot, remove_trailing_number_dot, flip_name
import re
from collections import defaultdict
from openlibrary.catalog.get_ia import get_from_archive, bad_ia_xml, marc_formats, urlopen_keep_trying
from openlibrary.catalog.marc.marc_binary import MarcBinary
from openlibrary.catalog.importer.db_read import get_mc
from openlibrary.catalog.marc.marc_xml import BadSubtag, BlankTag
from openlibrary.catalog.marc.marc_xml import read_marc_file, MarcXml, BlankTag, BadSubtag
from lxml import etree

subject_fields = set(['600', '610', '611', '630', '648', '650', '651', '662'])

re_flip_name = re.compile('^(.+), ([A-Z].+)$')

# 'Rhodes, Dan (Fictitious character)'
re_fictitious_character = re.compile('^(.+), (.+)( \(.* character\))$')
re_etc = re.compile('^(.+?)[, .]+etc[, .]?$', re.I)
re_comma = re.compile('^([A-Z])([A-Za-z ]+?) *, ([A-Z][A-Z a-z]+)$')

re_place_comma = re.compile('^(.+), (.+)$')
re_paren = re.compile('[()]')
def flip_place(s):
    s = remove_trailing_dot(s)
    # Whitechapel (London, England)
    # East End (London, England)
    # Whitechapel (Londres, Inglaterra)
    if re_paren.search(s):
        return s
    m = re_place_comma.match(s)
    return m.group(2) + ' ' + m.group(1) if m else s

def flip_subject(s):
    m = re_comma.match(s)
    if m:
        return m.group(3) + ' ' + m.group(1).lower()+m.group(2)
    else:
        return s

def four_types(i):
    want = set(['subject', 'time', 'place', 'person'])
    ret = dict((k, i[k]) for k in want if k in i)
    for j in (j for j in i.keys() if j not in want):
        for k, v in i[j].items():
            if 'subject' in ret:
                ret['subject'][k] = ret['subject'].get(k, 0) + v
            else:
                ret['subject'] = {k: v}
    return ret

archive_url = "http://archive.org/download/"

def bad_marc_alert(ia):
    from pprint import pformat
    msg_from = 'load_scribe@archive.org'
    msg_to = 'edward@archive.org'
    msg = '''\
From: %s
To: %s
Subject: bad MARC: %s

bad MARC: %s

''' % (msg_from, msg_to, ia, ia)

    import smtplib
    server = smtplib.SMTP('mail.archive.org')
    server.sendmail(msg_from, [msg_to], msg)
    server.quit()

def load_binary(ia):
    url = archive_url + ia + '/' + ia + '_meta.mrc'
    f = urlopen_keep_trying(url)
    data = f.read()
    assert '<title>Internet Archive: Page Not Found</title>' not in data[:200]
    if len(data) != int(data[:5]):
        data = data.decode('utf-8').encode('raw_unicode_escape')
    if len(data) != int(data[:5]):
        bad_marc_alert(ia)
        return
    return MarcBinary(data)

def load_xml(ia):
    url = archive_url + ia + '/' + ia + '_marc.xml'
    f = urlopen_keep_trying(url)
    root = etree.parse(f).getroot()
    if root.tag == '{http://www.loc.gov/MARC21/slim}collection':
        root = root[0]
    return MarcXml(root)

def subjects_for_work(rec):
    field_map = {
        'subject': 'subjects',
        'place': 'subject_places',
        'time': 'subject_times',
        'person': 'subject_people',
    }

    subjects = four_types(read_subjects(rec))

    return dict((field_map[k], v.keys()) for k, v in subjects.items())

re_edition_key = re.compile(r'^/(?:b|books)/(OL\d+M)$')

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

def bad_source_record(e, sr):
    from pprint import pformat
    import smtplib
    msg_from = 'marc_subject@archive.org'
    msg_to = 'edward@archive.org'
    msg = '''\
From: %s
To: %s
Subject: bad source record: %s

Bad source record: %s

%s
''' % (msg_from, msg_to, e['key'], sr, pformat(e))

    server = smtplib.SMTP('mail.archive.org')
    server.sendmail(msg_from, [msg_to], msg)
    server.quit()

re_ia_marc = re.compile('^(?:.*/)?([^/]+)_(marc\.xml|meta\.mrc)(:0:\d+)?$')
def get_work_subjects(w):
    found = set()
    for e in w['editions']:
        sr = e.get('source_records', [])
        if sr:
            for i in sr:
                if i.endswith('initial import'):
                    bad_source_record(e, i)
                    continue
                if i.startswith('ia:') or i.startswith('marc:'):
                    found.add(i)
                    continue
        else:
            m = re_edition_key.match(e['key'])
            mc = get_mc('/b/' + m.group(1))
            if mc:
                if mc.endswith('initial import'):
                    bad_source_record(e, mc)
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
            try:
                subjects.append(read_subjects(rec))
            except:
                print 'bad MARC:', loc
                print 'data:', `data`
                raise
        else:
            assert sr.startswith('ia:')
            subjects.append(get_subjects_from_ia(sr[3:]))
    return combine_subjects(subjects)

def tidy_subject(s):
    s = s.strip()
    if len(s) < 2:
        print 'short subject:', `s`
    else:
        s = s[0].upper() + s[1:]
    m = re_etc.search(s)
    if m:
        return m.group(1)
    s = remove_trailing_dot(s)
    m = re_fictitious_character.match(s)
    if m:
        return m.group(2) + ' ' + m.group(1) + m.group(3)
    m = re_comma.match(s)
    if m:
        return m.group(3) + ' ' + m.group(1) + m.group(2)
    return s

re_aspects = re.compile(' [Aa]spects$')
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

def read_subjects(rec):
    subjects = defaultdict(lambda: defaultdict(int))
    for tag, field in rec.read_fields(subject_fields):
        f = rec.decode_field(field)
        aspects = find_aspects(f)

        if tag == '600': # people
            name_and_date = []
            for k, v in f.get_subfields(['a', 'b', 'c', 'd']):
                v = '(' + v.strip('.() ') + ')' if k == 'd' else v.strip(' /,;:')
                if k == 'a':
                    m = re_flip_name.match(v)
                    if m:
                        v = flip_name(v)
                name_and_date.append(v)
            name = remove_trailing_dot(' '.join(name_and_date)).strip()
            if name != '':
                subjects['person'][name] += 1
        elif tag == '610': # org
            v = ' '.join(f.get_subfield_values('abcd'))
            v = v.strip()
            if v:
                v = remove_trailing_dot(v).strip()
            if v:
                v = tidy_subject(v)
            if v:
                subjects['org'][v] += 1

            for v in f.get_subfield_values('a'):
                v = v.strip()
                if v:
                    v = remove_trailing_dot(v).strip()
                if v:
                    v = tidy_subject(v)
                if v:
                    subjects['org'][v] += 1
        elif tag == '611': # event
            v = ' '.join(j.strip() for i, j in f.get_all_subfields() if i not in 'vxyz')
            if v:
                v = v.strip()
            v = tidy_subject(v)
            if v:
                subjects['event'][v] += 1
        elif tag == '630': # work
            for v in f.get_subfield_values(['a']):
                v = v.strip()
                if v:
                    v = remove_trailing_dot(v).strip()
                if v:
                    v = tidy_subject(v)
                if v:
                    subjects['work'][v] += 1
        elif tag == '650': # topical
            for v in f.get_subfield_values(['a']):
                if v:
                    v = v.strip()
                v = tidy_subject(v)
                if v:
                    subjects['subject'][v] += 1
        elif tag == '651': # geo
            for v in f.get_subfield_values(['a']):
                if v:
                    subjects['place'][flip_place(v).strip()] += 1

        for v in f.get_subfield_values(['y']):
            v = v.strip()
            if v:
                subjects['time'][remove_trailing_dot(v).strip()] += 1
        for v in f.get_subfield_values(['v']):
            v = v.strip()
            if v:
                v = remove_trailing_dot(v).strip()
            v = tidy_subject(v)
            if v:
                subjects['subject'][v] += 1
        for v in f.get_subfield_values(['z']):
            v = v.strip()
            if v:
                subjects['place'][flip_place(v).strip()] += 1
        for v in f.get_subfield_values(['x']):
            v = v.strip()
            if not v:
                continue
            if aspects and re_aspects.search(v):
                continue
            v = tidy_subject(v)
            if v:
                subjects['subject'][v] += 1

    return dict((k, dict(v)) for k, v in subjects.items())

def combine_subjects(subjects):
    all_subjects = defaultdict(lambda: defaultdict(int))
    for a in subjects:
        for b, c in a.items():
            for d, e in c.items():
                all_subjects[b][d] += e

    return dict((k, dict(v)) for k, v in all_subjects.items())
