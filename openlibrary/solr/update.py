from openlibrary.utils import str_to_key
import simplejson, re
from urllib import urlopen, quote_plus

re_escape = re.compile("([%s])" % re.escape(r'+-!(){}[]^"~*?:\\'))

solr_works = 'ol-solr:8983'
solr_subjects = 'ol-solr:8983'

def subject_count(field, subject):
    key = re_escape.sub(r'\\\1', str_to_key(subject)).encode('utf-8')
    data = urlopen('http://%s/solr/works/select?indent=on&wt=json&rows=0&q=%s_key:%s' % (solr_works, field, key)).read()
    try:
        ret = simplejson.loads(data)
    except:
        print data
        return 0
    return ret['response']['numFound']

def subject_need_update(key, count):
    escape_key = quote_plus(re_escape.sub(r'\\\1', key).encode('utf-8'))

    reply = urlopen('http://%s/solr/subjects/select?indent=on&wt=json&q=key:"%s"' % (solr_subjects, escape_key)).read()

    try:
        docs = simplejson.loads(reply)['response']['docs']
    except:
        print (key, escape_key)
        print reply
        raise
    if not docs:
        return True
    assert len(docs) == 1
    return count != docs[0]['count']

