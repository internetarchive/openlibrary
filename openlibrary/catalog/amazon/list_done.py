from lxml.html import fromstring, tostring
from openlibrary.catalog.utils.arc import read_arc, read_body
import re, os, sys

arc_dir = '/2/edward/amazon/arc'
total = 0
srtitle = 0
producttitle = 0

re_book_url = re.compile('^http://www.amazon.com/[^/]+/dp/([0-9A-Z]{10})/')
re_result_count = re.compile('^Showing ([,0-9]+) - ([,0-9]+) of ([,0-9]+) Results$')

bad_serp = 0

out = open('/2/edward/amazon/crawled2', 'w')

for filename in (i for i in os.listdir(arc_dir) if i.endswith('.arc')):
    print filename, total, srtitle, producttitle
    for url, wire in read_arc(arc_dir +'/' + filename):
        if url.startswith('file'):
            continue
        if not url.startswith('http://www.amazon.com/s?'):
            continue
        body = read_body(wire)
        doc = fromstring(body)
        found = []
        try:
            doc.get_element_by_id('noResultsTitle')
#            print 'no results:', url
            continue
        except KeyError:
            pass
        rc = doc.find_class('resultCount')
        if rc:
            m = re_result_count.match(rc[0].text)
            if m:
                (a, b, c) = map(lambda i: int(i.replace(',','')), m.groups())
                if a == c + 1 and b == c:
#                    print 'result count:', rc[0].text
#                    print 'empty page'
                    continue
        for e in doc.find_class('fastTrackList'):
            if e.text == 'This item is currently not available.':
                print e.text
                
        for pt in doc.find_class('productTitle'):
            assert pt.tag == 'div'
            assert pt[0].tag == 'a'
            href = pt[0].attrib['href']
            m = re_book_url.match(href)
            found.append(m.group(1))
            total += 1
            producttitle += 1

        for e in doc.find_class('srTitle'):
            td = e.getparent().getparent()
            assert td.tag == 'td'
            assert td[0].tag == 'a'
            href = td[0].attrib['href']
            m = re_book_url.match(href)
            found.append(m.group(1))
            total += 1
            srtitle += 1

        if len(found) == 0:
            print url
            bad_serp += 1
            open('bad_serp%d.html' % bad_serp, 'w').write(body)
        for asin in found:
            print >> out, asin
out.close()
