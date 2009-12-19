import re, urllib
from lxml.etree import parse, tostring

port = 8414

solr_chars = ['+','-','&&','||','!','(',')','{','}',
              '[',']','^','"','~','*','?',':','\\']

solr_char_pat = '|'.join(re.escape(i) for i in solr_chars)
re_solr_char = re.compile('(' + solr_char_pat + ')')

def url_quote(s):
    return urllib.quote_plus(s.encode('utf-8'))

def solr_esc(s):
    s = re_solr_char.sub(lambda m:''.join('\\' + i for i in m.group(1)), s)
    return url_quote(s)

def publisher_lookup(name):
   solr_select = "http://localhost:%d/solr/publishers/select" % port
   q = 'name:(%s)' % solr_esc(name)
   solr_select += "?indent=on&version=2.2&q.op=AND&q=%s&fq=&start=0&rows=100&fl=*%%2Cscore&qt=standard&wt=standard&explainOther=" % q
   reply = urllib.urlopen(solr_select)
   root = parse(reply).getroot()
   result = root.find('result')
   found = []
   for doc in result:
       score = float(doc.find("float[@name='score']").text)
       count = int(doc.find("int[@name='count']").text)
       name = doc.find("str[@name='name']").text
       found.append({'name': name, 'count': count, 'score': score})

   return found

def author_lookup(name):
   solr_select = "http://localhost:%d/solr/authors/select" % port
   q = 'name:(%s)' % solr_esc(name)
   solr_select += "?indent=on&version=2.2&q.op=AND&q=%s&fq=&start=0&rows=100&fl=*%%2Cscore&qt=standard&wt=standard&explainOther=" % q
   reply = urllib.urlopen(solr_select)
   root = parse(reply).getroot()
   result = root.find('result')
   found = []
   for doc in result:
       key = doc.find("str[@name='key']").text
       score = float(doc.find("float[@name='score']").text)
       name = doc.find("str[@name='name']").text
       found.append({'name': name, 'key': key, 'score': score})

   return found

if __name__ == '__main__':
    from pprint import pprint
    found = publisher_lookup('press')
    pprint(found)
    found = author_lookup('Plato')
    pprint(found)
