from catalog.merge.merge_marc import *
import catalog.merge.amazon as amazon
from catalog.get_ia import *
from catalog.importer.db_read import withKey, get_mc
import catalog.marc.fast_parse as fast_parse
import xml.parsers.expat
import dbhash

threshold = 875
index_path = '/1/pharos/edward/index/2/'
key_to_mc = dbhash.open(index_path + "key_to_mc.dbm", flag='r')
amazon.set_isbn_match(225)

def try_amazon(thing):
    if 'isbn_10' not in thing:
        return None
    if 'authors' in thing:
        authors = []
        for a in thing['authors']:
            author_thing = withKey(a['key'])
            if 'name' in author_thing:
                authors.append(author_thing['name'])
    else:
        authors = []
    return amazon.build_amazon(thing, authors)

def try_merge(e1, edition_key):
    ia = None
    mc = None
    if str(edition_key) in key_to_mc:
        mc = key_to_mc[str(edition_key)]
        if mc.startswith('ia:'):
            ia = mc[3:]
        elif mc.endswith('.xml') or mc.endswith('.mrc'):
            ia = mc[:mc.find('/')]
    if not mc or mc.startswith('amazon:'):
        thing = withKey(edition_key)
        if not thing:
            return False
        thing_type = thing['type']['key']
        if thing_type == '/type/delete': # 
            return False
        assert thing_type == '/type/edition'

    rec2 = None
    if ia:
        try:
            loc2, rec2 = get_ia(ia)
        except xml.parsers.expat.ExpatError:
            return False
        except urllib2.HTTPError, error:
            print error.code
            assert error.code in (404, 403)
        if not rec2:
            return True
    if not rec2:
        if not mc:
            mc = get_mc(thing['key'])
        if not mc:
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
        try:
            data = get_from_local(mc)
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

