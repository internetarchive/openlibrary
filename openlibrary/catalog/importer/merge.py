from openlibrary.catalog.merge.merge_marc import *
from openlibrary.catalog.read_rc import read_rc
import openlibrary.catalog.merge.amazon as amazon
from openlibrary.catalog.get_ia import *
from openlibrary.catalog.importer.db_read import withKey, get_mc
from openlibrary.api import OpenLibrary, Reference
import openlibrary.catalog.marc.fast_parse as fast_parse
import xml.parsers.expat
import web, sys
from time import sleep

rc = read_rc()

ol = OpenLibrary("http://openlibrary.org")
ol.login('ImportBot', rc['ImportBot']) 

ia_db = web.database(dbn='mysql', db='archive', user=rc['ia_db_user'], pw=rc['ia_db_pass'], host=rc['ia_db_host'])
ia_db.printing = False

re_meta_marc = re.compile('([^/]+)_(meta|marc)\.(mrc|xml)')

threshold = 875
amazon.set_isbn_match(225)

def try_amazon(thing):
    if 'isbn_10' not in thing:
        return None
    if 'authors' in thing:
        authors = []
        for a in thing['authors']:
            # this is a hack
            # the type of thing['authors'] should all be the same type
            if isinstance(a, dict):
                akey = a['key']
            else:
                assert isinstance(a, basestring)
                akey = a
            author_thing = withKey(akey)
            if 'name' in author_thing:
                authors.append(author_thing['name'])
    else:
        authors = []
    return amazon.build_amazon(thing, authors)

def is_dark_or_bad(ia):
    vars = { 'ia': ia }
    db_iter = None
    for attempt in range(5):
        try:
            db_iter = ia_db.query('select curatestate from metadata where identifier=$ia', vars)
            break
        except:
            print 'retry, attempt', attempt
            sleep(10)
    if db_iter is None:
        return False
    rows = list(db_iter)
    if len(rows) == 0:
        return True
    assert len(rows) == 1
    return rows[0].curatestate == 'dark'

def marc_match(e1, loc):
    print 'loc:', loc
    rec = fast_parse.read_edition(get_from_archive(loc))
    print 'rec:', rec
    try:
        e2 = build_marc(rec)
    except TypeError:
        print rec
        raise
    return attempt_merge(e1, e2, threshold, debug=False)

def ia_match(e1, ia):
    try:
        rec = get_ia(ia)
    except NoMARCXML:
        return False
    except urllib2.HTTPError:
        return False
    if rec is None or 'full_title' not in rec:
        return False
    try:
        e2 = build_marc(rec)
    except TypeError:
        print rec
        raise
    return attempt_merge(e1, e2, threshold, debug=False)

def amazon_match(e1, thing):
    try:
        a = try_amazon(thing)
    except IndexError:
        print thing['key']
        raise
    except AttributeError:
        return False
    if not a:
        return False
    try:
        return amazon.attempt_merge(a, e1, threshold, debug=False)
    except:
        print a
        print e1
        print thing['key']
        raise

def fix_source_records(key, thing):
    if 'source_records' not in thing:
        return False
    src_rec = thing['source_records']
    marc_ia = 'marc:ia:'
    if not any(i.startswith(marc_ia) for i in src_rec):
        return False
    e = ol.get(key)
    new = [i[5:] if i.startswith(marc_ia) else i for i in e['source_records']]
    e['source_records'] = new
    print e['ocaid']
    print e['source_records']
    assert 'ocaid' in e and ('ia:' + e['ocaid'] in e['source_records'])
    print 'fix source records'
    print ol.save(key, e, 'fix bad source records')
    return True

def source_records_match(e1, thing):
    marc = 'marc:'
    amazon = 'amazon:'
    ia = 'ia:'
    match = False
    for src in thing['source_records']:
        if src == 'marc:initial import':
            continue
        # hippocrates01hippuoft/hippocrates01hippuoft_marc.xml
        m = re_meta_marc.search(src)
        if m:
            src = 'ia:' + m.group(1)
        if src.startswith(marc):
            if marc_match(e1, src[len(marc):]):
                match = True
                break
        elif src.startswith(ia):
            if ia_match(e1, src[len(ia):]):
                match = True
                break
        else:
            assert src.startswith(amazon)
            if amazon_match(e1, thing):
                match = True
                break
    return match

def try_merge(e1, edition_key, thing):
    thing_type = thing['type']
    if thing_type != Reference('/type/edition'):
        print thing['key'], 'is', str(thing['type'])
    if thing_type == Reference('/type/delete'):
        return False
    assert thing_type == Reference('/type/edition')

    if 'source_records' in thing:
        if fix_source_records(edition_key, thing):
            thing = withKey(edition_key) # reload
        return source_records_match(e1, thing)

    ia = thing.get('ocaid', None)
    print edition_key
    mc = get_mc(edition_key)
    print mc
    if mc:
        if mc.startswith('ia:'):
            ia = mc[3:]
        elif mc.endswith('.xml') or mc.endswith('.mrc'):
            ia = mc[:mc.find('/')]
        if '_meta.mrc:' in mc:
            print thing
            if 'ocaid' not in thing:
                return False
            ia = thing['ocaid']
    rec2 = None
    if ia:
        if is_dark_or_bad(ia):
            return False
        try:
            rec2 = get_ia(ia)
        except xml.parsers.expat.ExpatError:
            return False
        except NoMARCXML:
            print 'no MARCXML'
            pass
        except urllib2.HTTPError, error:
            print error.code
            assert error.code in (404, 403)
        if not rec2:
            return True
    if not rec2:
        if not mc:
            mc = get_mc(thing['key'])
        if not mc or mc == 'initial import':
            return False
        if mc.startswith('amazon:'):
            try:
                a = try_amazon(thing)
            except IndexError:
                print thing['key']
                raise
            except AttributeError:
                return False
            if not a:
                return False
            try:
                return amazon.attempt_merge(a, e1, threshold, debug=False)
            except:
                print a
                print e1
                print thing['key']
                raise
        print 'mc:', mc
        try:
            assert not mc.startswith('ia:')
            data = get_from_archive(mc)
            if not data:
                return True
            rec2 = fast_parse.read_edition(data)
        except (fast_parse.SoundRecording, IndexError, AssertionError):
            print mc
            print edition_key
            return False
        except:
            print mc
            print edition_key
            raise
    if not rec2:
        return False
    try:
        e2 = build_marc(rec2)
    except TypeError:
        print rec2
        raise
    return attempt_merge(e1, e2, threshold, debug=False)
