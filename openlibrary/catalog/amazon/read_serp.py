from lxml.html import fromstring
from openlibrary.catalog.utils.arc import read_arc, read_body
import os, re

arc_dir = '/2/edward/amazon/arc'

re_book_url = re.compile('^http://www.amazon.com/[^/]+/dp/([0-9A-Z]{10})/')
re_result_count = re.compile('^Showing ([,0-9]+) - ([,0-9]+) of ([,0-9]+) Results$')
re_title = re.compile('<title>Amazon.com: (.*?)(:?, Page \d+)?</title>')
crawled = set(i[:-1] for i in open('/2/edward/amazon/crawled'))

# /2/edward/amazon/arc/20100311*.arc

def find_pt(doc):
    found = []
    for pt in doc.find_class('productTitle'):
        assert pt.tag == 'div'
        assert pt[0].tag == 'a'
        href = pt[0].attrib['href']
        m = re_book_url.match(href)
        print m.group(1)
        found.append(m.group(1))
    return found

def find_srtitle(doc):
    found = []
    for e in doc.find_class('srTitle'):
        td = e.getparent().getparent()
        assert td.tag == 'td'
        assert td[0].tag == 'a'
        href = td[0].attrib['href']
        m = re_book_url.match(href)
        found.append(m.group(1))
    return found

found_books = set()

prev = ''
#out = open('/2/edward/amazon/best_sellers2', 'w')
for filename in (i for i in os.listdir(arc_dir) if i.endswith('.arc')):
    if not filename.startswith('20100412'):
        continue
    for url, wire in read_arc(arc_dir +'/' + filename):
        #print filename, url
        if url.startswith('file'):
            continue
        if not url.startswith('http://www.amazon.com/s?'):
            continue
        body = read_body(wire)
        m = re_title.search(body)
        if m.group(1) != prev:
            print m.group(1)
            prev = m.group(1)
        continue
        doc = fromstring(body)
        try:
            doc.get_element_by_id('noResultsTitle')
            continue
        except KeyError:
            pass
        rc = doc.find_class('resultCount')
        if rc:
            m = re_result_count.match(rc[0].text)
            if m:
                (a, b, c) = map(lambda i: int(i.replace(',','')), m.groups())
                if a == c + 1 and b == c:
                    continue
        for e in doc.find_class('fastTrackList'):
            if e.text == 'This item is currently not available.':
                print e.text

        assert len(find_pt(doc)) == 0
        serp_found = find_srtitle(doc)
        for asin in serp_found:
            if asin in crawled:
                continue
            if asin not in found_books:
                print >> out, asin
        found_books.update(serp_found)
        print len(serp_found), len(found_books), filename, url

#out.close()
