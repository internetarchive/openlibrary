#!/usr/bin/python

# find works and create pages on production

import re, sys, web, urllib2
from openlibrary.solr.add_covers import add_cover_to_work
from openlibrary.solr.update_work import update_work, solr_update, update_author
from openlibrary.catalog.get_ia import get_from_archive, get_data
from openlibrary.catalog.marc.fast_parse import get_subfield_values, get_first_tag, get_tag_lines, get_subfields, BadDictionary
from openlibrary.catalog.utils.query import query_iter, withKey
from openlibrary.catalog.utils import mk_norm
from openlibrary.catalog.read_rc import read_rc
from collections import defaultdict
from pprint import pprint, pformat
from openlibrary.catalog.utils.edit import fix_edition
from openlibrary.catalog.importer.db_read import get_mc
from urllib import urlopen
from openlibrary.api import OpenLibrary
from lxml import etree
from time import sleep, time, strftime
from openlibrary.catalog.marc.marc_subject import get_work_subjects, four_types
import simplejson as json

ol = OpenLibrary("http://openlibrary.org")

re_skip = re.compile('\b([A-Z]|Co|Dr|Jr|Capt|Mr|Mrs|Ms|Prof|Rev|Revd|Hon|etc)\.$')
re_work_key = re.compile('^/works/OL(\d+)W$')
re_lang_key = re.compile('^/(?:l|languages)/([a-z]{3})$')
re_author_key = re.compile('^/(?:a|authors)/(OL\d+A)$')

re_ia_marc = re.compile('^(?:.*/)?([^/]+)_(marc\.xml|meta\.mrc)(:0:\d+)?$')

ns = '{http://www.loc.gov/MARC21/slim}'
ns_leader = ns + 'leader'
ns_data = ns + 'datafield'

def has_dot(s):
    return s.endswith('.') and not re_skip.search(s)

def get_with_retry(k):
    for attempt in range(50):
        try:
            return ol.get(k)
        except:
            pass
        print 'retry'
        sleep(5)
    return ol.get()

#set_staging(True)

# sample title: The Dollar Hen (Illustrated Edition) (Dodo Press)
re_parens = re.compile('^(.*?)(?: \(.+ (?:Edition|Press|Print|Plays|Collection|Publication|Novels|Mysteries|Book Series|Classics Library|Classics|Books)\))+$', re.I)

def top_rev_wt(d):
    d_sorted = sorted(d.keys(), cmp=lambda i, j: cmp(d[j], d[i]) or cmp(len(j), len(i)))
    return d_sorted[0]

def books_query(akey): # live version
    q = {
        'type':'/type/edition',
        'authors': akey,
        'source_records': None,
        'title': None,
        'work_title': None,
        'table_of_contents': None,
        'languages': None,
        'title_prefix': None,
        'subtitle': None,
    }
    return query_iter(q)

def freq_dict_top(d):
    return sorted(d.keys(), reverse=True, key=lambda i:d[i])[0]

def get_marc_src(e):
    mc = get_mc(e['key'])
    if mc and mc.startswith('amazon:'):
        mc = None
    if mc and mc.startswith('ia:'):
        yield 'ia', mc[3:]
    elif mc:
        m = re_ia_marc.match(mc)
        if m:
            yield 'ia', m.group(1)
        else:
            yield 'marc', mc
    source_records = e.get('source_records', [])
    if not source_records:
        return
    for src in source_records:
        if src.startswith('ia:'):
            if not mc or src != mc:
                yield 'ia', src[3:]
            continue
        if src.startswith('marc:'):
            if not mc or src != 'marc:' + mc:
                yield 'marc', src[5:]
            continue

def get_ia_work_title(ia):
    url = 'http://www.archive.org/download/' + ia + '/' + ia + '_marc.xml'
    try:
        root = etree.parse(urlopen(url)).getroot()
    except KeyboardInterrupt:
        raise
    except:
        return
    e = root.find(ns_data + "[@tag='240']")
    if e is None:
        return
    wt = ' '.join(s.text for s in e if s.attrib['code'] == 'a' and s.text)
    return wt

def get_work_title(e):
    # use first work title we find in source MARC records
    wt = None
    for src_type, src in get_marc_src(e):
        if src_type == 'ia':
            wt = get_ia_work_title(src)
            if wt:
                wt = wt.strip('. ')
            if wt:
                break
            continue
        assert src_type == 'marc'
        data = None
        try:
            data = get_data(src)
        except ValueError:
            print 'bad record source:', src
            print 'http://openlibrary.org' + e['key']
            continue
        except urllib2.HTTPError, error:
            print 'HTTP error:', error.code, error.msg
            print e['key']
        if not data:
            continue
        is_marc8 = data[9] != 'a'
        try:
            line = get_first_tag(data, set(['240']))
        except BadDictionary:
            print 'bad dictionary:', src
            print 'http://openlibrary.org' + e['key']
            continue
        if line:
            wt = ' '.join(get_subfield_values(line, ['a'], is_marc8)).strip('. ')
            break
    if wt:
        return wt
    if e.get('work_titles', []):
        return e['work_titles'][0].strip('. ')
    if e.get('work_title', []):
        return e['work_title'][0].strip('. ')

# don't use any of these as work titles
bad_titles = ['Publications', 'Works. English', 'Missal', 'Works', 'Report', \
    'Letters', 'Calendar', 'Bulletin', 'Plays', 'Sermons', 'Correspondence', \
    'Bill', 'Bills', 'Selections', 'Selected works', 'Selected works. English', \
    'The Novels', 'Laws, etc']

def get_books(akey, query):
    for e in query:
        try:
            if not e.get('title', None):
                continue
        except:
            print e
#        if len(e.get('authors', [])) != 1:
#            continue
        if 'title_prefix' in e and e['title_prefix']:
            prefix = e['title_prefix']
            if prefix[-1] != ' ':
                prefix += ' '
            title = prefix + e['title']
        else:
            title = e['title']

        title = title.strip(' ')
        if has_dot(title):
            title = title[:-1]

        m = re_parens.match(title)
        if m:
            title = m.group(1)

        n = mk_norm(title)

        book = {
            'title': title,
            'norm_title': n,
            'key': e['key'],
        }

        lang = e.get('languages', [])
        if lang:
            book['lang'] = [re_lang_key.match(l['key']).group(1) for l in lang]

        if e.get('table_of_contents', None):
            if isinstance(e['table_of_contents'][0], basestring):
                book['table_of_contents'] = e['table_of_contents']
            else:
                assert isinstance(e['table_of_contents'][0], dict)
                if e['table_of_contents'][0].get('type', None) == '/type/text':
                    book['table_of_contents'] = [i['value'] for i in e['table_of_contents']]
        if 'subtitle' in e:
            book['subtitle'] = e['subtitle']

        if 'source_records' in e:
            book['source_records'] = e['source_records']

        wt = get_work_title(e)
        if not wt:
            yield book
            continue
        if wt in bad_titles:
            yield book
            continue
        n_wt = mk_norm(wt)
        book['work_title'] = wt
        book['norm_wt'] = n_wt
        yield book

def build_work_title_map(equiv, norm_titles):
    # map of normalized book titles to normalized work titles
    title_to_work_title = defaultdict(set)
    for (norm_title, norm_wt), v in equiv.items():
        if v != 1:
            title_to_work_title[norm_title].add(norm_wt)

    title_map = {}
    for norm_title, work_titles in title_to_work_title.items():
        if len(work_titles) == 1:
            title_map[norm_title] = list(work_titles)[0]
            continue
        most_common_title = max(work_titles, key=lambda i:norm_titles[i])
        if norm_title != most_common_title:
            title_map[norm_title] = most_common_title
        for work_title in work_titles:
            if work_title != most_common_title:
                title_map[work_title] = most_common_title
    return title_map

def get_first_version(key):
    url = 'http://openlibrary.org' + key + '.json?v=1'
    try:
        return json.load(urlopen(url))
    except:
        print url
        raise

def get_existing_works(akey):
    q = {
        'type':'/type/work',
        'authors': {'author': {'key': akey}},
        'limit': 0,
    }
    seen = set()
    for wkey in ol.query(q):
        if wkey in seen:
            continue # skip dups
        if wkey.startswith('DUP'):
            continue
        try:
            w = get_with_retry(wkey)
        except:
            print wkey
            raise
        if w['type'] in ('/type/redirect', '/type/delete'):
            continue
        if w['type'] != '/type/work':
            print 'infobase error, should only return works'
            print q
            print w['key']
        assert w['type'] == '/type/work'
        yield w

def find_title_redirects(akey):
    title_redirects = {}
    for w in get_existing_works(akey):
        try:
            norm_wt = mk_norm(w['title'])
        except:
            print w['key']
            raise
        q = {'type':'/type/redirect', 'location': str(w['key']), 'limit': 0}
        try:
            query_iter = ol.query(q)
        except:
            print q
            raise
        for r in map(get_first_version, query_iter):
            redirect_history = json.load(urlopen('http://openlibrary.org%s.json?m=history' % r['key']))
            if any(v['author'].endswith('/WorkBot') and v['comment'] == "merge works" for v in redirect_history):
                continue
            #print 'redirect:', r
            if mk_norm(r['title']) == norm_wt:
                continue
            if r['title'] in title_redirects:
                assert title_redirects[r['title']] == w['title']
            #print 'redirect:', r['key'], r['title'], 'work:', w['key'], w['title']
            title_redirects[r['title']] = w['title']
    return title_redirects

def find_works(akey, book_iter, existing={}):
    equiv = defaultdict(int) # normalized title and work title pairs
    norm_titles = defaultdict(int) # frequency of titles
    books_by_key = {}
    books = []
    # normalized work title to regular title
    rev_wt = defaultdict(lambda: defaultdict(int))

    for book in book_iter:
        if 'norm_wt' in book:
            pair = (book['norm_title'], book['norm_wt'])
            equiv[pair] += 1
            rev_wt[book['norm_wt']][book['work_title']] +=1
        norm_titles[book['norm_title']] += 1 # used to build title_map
        books_by_key[book['key']] = book
        books.append(book)

    title_map = build_work_title_map(equiv, norm_titles)

    for a, b in existing.items():
        norm_a = mk_norm(a)
        norm_b = mk_norm(b)
        rev_wt[norm_b][norm_a] +=1
        title_map[norm_a] = norm_b

    works = defaultdict(lambda: defaultdict(list))
    work_titles = defaultdict(list)
    for b in books:
        if 'eng' not in b.get('lang', []) and 'norm_wt' in b:
            work_titles[b['norm_wt']].append(b['key'])
        n = b['norm_title']
        title = b['title']
        if n in title_map:
            n = title_map[n]
            title = top_rev_wt(rev_wt[n])
        works[n][title].append(b['key'])

    works = sorted([(sum(map(len, w.values() + [work_titles[n]])), n, w) for n, w in works.items()])

    for work_count, norm, w in works:
        first = sorted(w.items(), reverse=True, key=lambda i:len(i[1]))[0][0]
        titles = defaultdict(int)
        for key_list in w.values():
            for ekey in key_list:
                b = books_by_key[ekey]
                title = b['title']
                titles[title] += 1
        keys = work_titles[norm]
        for values in w.values():
            keys += values
        assert work_count == len(keys)
        title = max(titles.keys(), key=lambda i:titles[i])
        toc_iter = ((k, books_by_key[k].get('table_of_contents', None)) for k in keys)
        toc = dict((k, v) for k, v in toc_iter if v)
        editions = [books_by_key[k] for k in keys]
        subtitles = defaultdict(lambda: defaultdict(int))
        edition_count = 0
        with_subtitle_count = 0
        for e in editions:
            edition_count += 1
            subtitle = e['subtitle'] or ''
            if subtitle != '':
                with_subtitle_count += 1
            norm_subtitle = mk_norm(subtitle)
            if norm_subtitle != norm:
                subtitles[norm_subtitle][subtitle] += 1
        use_subtitle = None
        for k, v in subtitles.iteritems():
            lc_k = k.strip(' .').lower()
            if lc_k in ('', 'roman') or 'edition' in lc_k:
                continue
            num = sum(v.values())
            overall = float(num) / float(edition_count)
            ratio = float(num) / float(with_subtitle_count)
            if overall > 0.2 and ratio > 0.5:
                use_subtitle = freq_dict_top(v)
        w = {'title': first, 'editions': editions}
        if use_subtitle:
            w['subtitle'] = use_subtitle
        if toc:
            w['toc'] = toc
        try:
            subjects = four_types(get_work_subjects(w))
        except:
            print w
            raise
        if subjects:
            w['subjects'] = subjects
        yield w

def print_works(works):
    for w in works:
        print len(w['editions']), w['title']
        print '   ', [e['key'] for e in w['editions']]
        print '   ', w.get('subtitle', None)
        print '   ', w.get('subjects', None)


def books_from_cache():
    for line in open('book_cache'):
        yield eval(line)

def add_subjects_to_work(subjects, w):
    mapping = {
        'subject': 'subjects',
        'place': 'subject_places',
        'time': 'subject_times',
        'person': 'subject_people',
    }
    for k, v in subjects.items():
        k = mapping[k]
        subjects = [i[0] for i in sorted(v.items(), key=lambda i:i[1], reverse=True) if i != '']
        existing_subjects = set(w.get(k, []))
        w.setdefault(k, []).extend(s for s in subjects if s not in existing_subjects)
        try:
            assert all(i != '' and not i.endswith(' ') for i in w[k])
        except AssertionError:
            print 'subjects end with space'
            print w
            print subjects
            raise

def add_detail_to_work(i, j):
    if 'subtitle' in i:
        j['subtitle'] = i['subtitle']
    if 'subjects' in i:
        add_subjects_to_work(i['subjects'], j)

def fix_up_authors(w, akey, editions):
    #print (w, akey, editions)
    seen_akey = False
    need_save = False
    for a in w.get('authors', []):
        obj = withKey(a['author']['key'])
        if obj['type']['key'] == '/type/redirect':
            a['author']['key'] = obj['location']
            a['author']['key'] = '/authors/' + re_author_key.match(a['author']['key']).group(1)
            #print 'getting:', a['author']['key']
            obj = withKey(a['author']['key'])
            #print 'found:', obj
            assert obj['type']['key'] == '/type/author'
            need_save = True
        if akey == a['author']['key']:
            seen_akey = True
    if seen_akey:
        return need_save
    try:
        ekey = editions[0]['key']
    except:
        print 'editions:', editions
        raise
    #print 'author %s missing. copying from first edition %s' % (akey, ekey)
    #print 'before:'
    for a in w.get('authors', []):
        print a
    e = withKey(ekey)
    #print e
    if not e.get('authors', None):
        #print 'no authors in edition'
        return
    w['authors'] = [{'type':'/type/author_role', 'author':a} for a in e['authors']]
    #print 'after:'
    #for a in w['authors']:
    #    print a
    return True

def new_work(akey, w, do_updates, fh_log):
    ol_work = {
        'title': w['title'],
        'type': '/type/work',
        'authors': [{'type':'/type/author_role', 'author': akey}],
    }
    add_detail_to_work(w, ol_work)
    print >> fh_log, ol_work
    if do_updates:
        for attempt in range(5):
            try:
                wkey = ol.new(ol_work, comment='work found')
                break
            except:
                if attempt == 4:
                    raise
                print 'retrying: %d attempt' % attempt
        print >> fh_log, 'new work:', wkey, `w['title']`
    else:
        print >> fh_log, 'new work:', `w['title']`
    update = []
    for e in w['editions']:
        try:
            e = ol.get(e['key'])
        except:
            print 'edition:', e['key']
            raise
        if do_updates:
            e['works'] = [{'key': wkey}]
        assert e['type'] == '/type/edition'
        update.append(e)
    if do_updates:
        try:
            print >> fh_log, ol.save_many(update, "add editions to new work")
        except:
            pprint(update)
            # raise # ignore errors
        return [wkey]
    return []

def update_work_with_best_match(akey, w, work_to_edition, do_updates, fh_log):
    work_updated = []
    best = w['best_match']['key']
    update = []
    subjects_from_existing_works = defaultdict(set)
    for wkey in w['existing_works'].iterkeys():
        if wkey == best:
            continue
        existing = get_with_retry(wkey)
        for k in 'subjects', 'subject_places', 'subject_times', 'subject_people':
            if existing.get(k):
                subjects_from_existing_works[k].update(existing[k])

        update.append({'type': '/type/redirect', 'location': best, 'key': wkey})
        work_updated.append(wkey)

    for wkey in w['existing_works'].iterkeys():
        editions = set(work_to_edition[wkey])
        editions.update(e['key'] for e in w['editions'])
        for ekey in editions:
            e = get_with_retry(ekey)
            e['works'] = [{'key': best}]
            authors = []
            for akey in e['authors']:
                a = get_with_retry(akey)
                if a['type'] == '/type/redirect':
                    m = re_author_key.match(a['location'])
                    akey = '/authors/' + m.group(1)
                authors.append({'key': str(akey)})
            e['authors'] = authors
            update.append(e)

    cur_work = w['best_match']
    need_save = fix_up_authors(cur_work, akey, w['editions']) 
    if any(subjects_from_existing_works.values()):
        need_save = True
    if need_save or cur_work['title'] != w['title'] \
            or ('subtitle' in w and 'subtitle' not in cur_work) \
            or ('subjects' in w and 'subjects' not in cur_work):
        if cur_work['title'] != w['title']:
            print 'update work title:', best, `cur_work['title']`, '->', `w['title']`
        existing_work = get_with_retry(best)
        if existing_work['type'] != '/type/work':
            pprint(existing_work)
        assert existing_work['type'] == '/type/work'
        existing_work['title'] = w['title']
        for k, v in subjects_from_existing_works.items():
            existing_subjects = set(existing_work.get(k, []))
            existing_work.setdefault(k, []).extend(s for s in v if s not in existing_subjects)
        add_detail_to_work(w, existing_work)
        print >> fh_log, 'existing:', existing_work
        print >> fh_log, 'subtitle:', `existing_work['subtitle']` if 'subtitle' in existing_work else 'n/a'
        update.append(existing_work)
        work_updated.append(best)
    if do_updates:
        try:
            print >> fh_log, ol.save_many(update, 'merge works')
        except:
            for page in update:
                print page
            raise
    return work_updated

def update_works(akey, works, do_updates=False):
    # we can now look up all works by an author   
    if do_updates:
        rc = read_rc()
        ol.login('WorkBot', rc['WorkBot']) 

    fh_log = open('/1/openlibrary/log/work_finder/' + strftime('%F_%T'), 'w')
    works = list(works)
    print >> fh_log, akey
    print >> fh_log, 'works:'
    pprint(works, fh_log)

    while True: # until redirects repaired
        q = {'type':'/type/edition', 'authors': akey, 'works': None}
        work_to_edition = defaultdict(set)
        edition_to_work = defaultdict(set)
        for e in query_iter(q):
            if not isinstance(e, dict):
                continue
            if e.get('works', None):
                for w in e['works']:
                    work_to_edition[w['key']].add(e['key'])
                    edition_to_work[e['key']].add(w['key'])

        work_by_key = {}
        fix_redirects = []
        for k, editions in work_to_edition.items():
            w = withKey(k)
            if w['type']['key'] == '/type/redirect':
                wkey = w['location']
                print >> fh_log, 'redirect found', w['key'], '->', wkey, editions
                assert re_work_key.match(wkey)
                for ekey in editions:
                    e = get_with_retry(ekey)
                    e['works'] = [{'key': wkey}]
                    fix_redirects.append(e)
                continue
            work_by_key[k] = w
        if not fix_redirects:
            print >> fh_log, 'no redirects left'
            break
        print >> fh_log, 'save redirects'
        try:
            ol.save_many(fix_redirects, "merge works")
        except:
            for r in fix_redirects:
                print r
            raise

    all_existing = set()
    work_keys = []
    print >> fh_log, 'edition_to_work:'
    print >> fh_log, `dict(edition_to_work)`
    print >> fh_log
    print >> fh_log, 'work_to_edition'
    print >> fh_log, `dict(work_to_edition)`
    print >> fh_log

#    open('edition_to_work', 'w').write(`dict(edition_to_work)`)
#    open('work_to_edition', 'w').write(`dict(work_to_edition)`)
#    open('work_by_key', 'w').write(`dict(work_by_key)`)

    work_title_match = {}
    works_by_title = {}
    for w in works: # 1st pass
        for e in w['editions']:
            ekey = e['key'] if isinstance(e, dict) else e
            for wkey in edition_to_work.get(ekey, []):
                try:
                    wtitle = work_by_key[wkey]['title']
                except:
                    print 'bad work:', wkey
                    raise
                if wtitle == w['title']:
                    work_title_match[wkey] = w['title']

    wkey_to_new_title = defaultdict(set)

    for w in works: # 2nd pass
        works_by_title[w['title']] = w
        w['existing_works'] = defaultdict(int)
        for e in w['editions']:
            ekey = e['key'] if isinstance(e, dict) else e
            for wkey in edition_to_work.get(ekey, []):
                if wkey in work_title_match and work_title_match[wkey] != w['title']:
                    continue
                wtitle = work_by_key[wkey]['title']
                w['existing_works'][wkey] += 1
                wkey_to_new_title[wkey].add(w['title'])

    existing_work_with_conflict = defaultdict(set)

    for w in works: # 3rd pass
        for wkey, v in w['existing_works'].iteritems():
            if any(title != w['title'] for title in wkey_to_new_title[wkey]):
                w['has_conflict'] = True
                existing_work_with_conflict[wkey].add(w['title'])
                break

    for wkey, v in existing_work_with_conflict.iteritems():
        cur_work = work_by_key[wkey]
        existing_titles = defaultdict(int)
        for ekey in work_to_edition[wkey]:
            e = withKey(ekey)
            title = e['title']
            if e.get('title_prefix', None):
                title = e['title_prefix'].strip() + ' ' + e['title']
            existing_titles[title] += 1
        best_match = max(v, key=lambda wt: existing_titles[wt])
        works_by_title[best_match]['best_match'] = work_by_key[wkey]
        for wtitle in v:
            del works_by_title[wtitle]['has_conflict']
            if wtitle != best_match:
                works_by_title[wtitle]['existing_works'] = {}

    def other_matches(w, existing_wkey):
        return [title for title in wkey_to_new_title[existing_wkey] if title != w['title']]

    works_updated_this_session = set()

    for w in works: # 4th pass
        if 'has_conflict' in w:
            pprint(w)
        assert 'has_conflict' not in w
        if len(w['existing_works']) == 1:
            existing_wkey = w['existing_works'].keys()[0]
            if not other_matches(w, existing_wkey):
                w['best_match'] = work_by_key[existing_wkey]
        if 'best_match' in w:
            updated = update_work_with_best_match(akey, w, work_to_edition, do_updates, fh_log)
            for wkey in updated:
                if wkey in works_updated_this_session:
                    print >> fh_log, wkey, 'already updated!'
                    print wkey, 'already updated!'
                works_updated_this_session.update(updated)
            continue
        if not w['existing_works']:
            updated = new_work(akey, w, do_updates, fh_log)
            for wkey in updated:
                assert wkey not in works_updated_this_session
                works_updated_this_session.update(updated)
            continue

        assert not any(other_matches(w, wkey) for wkey in w['existing_works'].iterkeys())
        best_match = max(w['existing_works'].iteritems(), key=lambda i:i[1])[0]
        w['best_match'] = work_by_key[best_match]
        updated = update_work_with_best_match(akey, w, work_to_edition, do_updates, fh_log)
        for wkey in updated:
            if wkey in works_updated_this_session:
                print >> fh_log, wkey, 'already updated!'
                print wkey, 'already updated!'
        works_updated_this_session.update(updated)

    #if not do_updates:
    #    return []

    return [withKey(key) for key in works_updated_this_session]

if __name__ == '__main__':
    akey = '/authors/' + sys.argv[1]

    title_redirects = find_title_redirects(akey)
    works = find_works(akey, get_books(akey, books_query(akey)), existing=title_redirects)
    to_update = update_works(akey, works, do_updates=True)

    requests = []
    for w in to_update:
        requests += update_work(w)

    if to_update:
        solr_update(requests + ['<commit />'], debug=True)

    requests = update_author(akey)
    solr_update(requests + ['<commit/>'], index='authors', debug=True)
