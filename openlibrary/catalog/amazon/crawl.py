from lxml.html import parse, tostring, fromstring
import re, sys
from urllib import unquote
from urllib2 import urlopen
from time import sleep
from os.path import exists
from datetime import date, timedelta
import codecs

re_expect_end = re.compile('</div>\n</body>\n</html>[ \n]*$')

def percent(a, b):
    return float(a * 100.0) / b

page_size = 12
max_pages = 100
max_results = page_size * max_pages

re_product_title = re.compile('/dp/([^/]*)')
re_result_count = re.compile('Showing (?:[\d,]+ - [\d,]+ of )?([\d,]+) Result')
re_rh_n = re.compile('rh=n%3A(\d+)%2C')
re_facet_count = re.compile(u'^\xa0\(([\d,]+)\)$')

base_url = "http://amazon.com/s?ie=UTF8&rh="
rh = 'i:stripbooks,p_n_feature_browse-bin:618083011,p_n_date:'

out_dir = '/1/edward/amazon/crawl'
out_dir = '/home/edward/amazon/crawl'

def get_url(params):
    filename = 'cache/' + params
    for i in range(10):
        try:
            url = base_url + rh + params
            print url
            req = urlopen(url)
            page = req.read()
            break
        except IOError:
            if i == 9:
                raise
            pass
        sleep(2)
    #open(filename, 'w').write(page)
    return fromstring(page)

def get_page(params):
    return get_url(params) # no cache
    filename = 'cache/' + params
    if exists(filename):
        root = parse(filename).getroot()
    else:
        root = get_url(params)
    return root

def get_total(root):
    e = root.find(".//td[@class='resultCount']")
    if e is None:
        return
    return int(re_result_count.match(e.text).group(1).replace(',', ''))

def read_books(params, root):
    # sometimes there is no link, bug at Amazaon
    # either skip it, or reload the page
    for i in range(5):
        book_links = [e.find('.//a[@href]') for e in root.find_class('dataColumn')]
        if all(a is not None for a in book_links):
            break
        sleep(2)
        print 'retry:', params
        root = get_url(params)

    return [re_product_title.search(a.attrib['href']).group(1) for a in book_links if a is not None]

def get_cats(root):
    cats = []
    for div in root.find_class('narrowItemHeading'):
        if div.text != 'Department':
            continue
        container = div.getparent()
        assert container.tag == 'td' and container.attrib['class'] == 'refinementContainer'
        break

    table = container.find('table')
    for e in table.iterfind(".//div[@class='refinement']"):
        a = e[0]
        assert a.tag == 'a'
        span1 = a[0]
        assert span1.tag == 'span' and span1.attrib['class'] == 'refinementLink'
        span2 = a[1]
        assert span2.tag == 'span' and span2.attrib['class'] == 'narrowValue'
        href = a.attrib['href']
        m1 = re_rh_n.search(href)
        m2 = re_facet_count.search(span2.text)
        cats.append((int(m1.group(1)), span1.text, int(m2.group(1).replace(',',''))))
        
    return cats

    for e in container.find('table').find_class('refinementLink'):
        a = e.getparent()
        assert a.tag == 'a'
        cat = { 'url': a.attrib['href'], 'title': e.text }
        href = a.attrib['href']
        m = re_rh_n.search(href)
        cats.append((int(m.group(1)), e.text))

def read_page(cur_date):
    params = cur_date.strftime("%Y%m%d")
    root = get_page(params)
    total = get_total(root)
    if total is None:
        print 'no books on', cur_date
        return 0, set(), []
    grand_total = total
    pages = (total / page_size) + 1
    print 'total:', total, 'pages:', pages

    cats = get_cats(root)
    #return grand_total, [], cats

    books = set()

    books.update(read_books(params, root))
    for page in range(2, min((pages, 100))+1):
        params_with_page = params + "&page=%d" % page
        books.update(read_books(params_with_page, get_page(params_with_page)))
        print page, len(books)

    print len(books)

#    for order_by in ('-price', 'price', '-editionspsrank'):
#        print order_by
#        for page in range(1, min((pages, 100))+1):
#            params_with_page = params + "&page=%d&sort=%s" % (page, order_by)
#            cur = read_books(params_with_page, get_page(params_with_page))
#            books.update(cur)
#            print order_by, page, len(books), len(cur)
#        print order_by, len(books)
#
#    return

    cats = get_cats(root)
    print 'cat total:', sum(i[2] for i in cats)
    if total > max_results:
        for n, title, count in cats:
            print `n, title, count`
            params_with_cat = params + ",n:" + str(n)
            root = get_page(params_with_cat)
            cat_total = get_total(root)
            pages = (cat_total / page_size) + 1
            print 'cat_total:', total, 'pages:', total / page_size
            if cat_total > max_results:
                print 'cat_total (%d) > max results (%d)' % (total, max_results)
    #        assert cat_total <= max_results
            books.update(read_books(params_with_cat, root))
            for page in range(2, min((pages, 100)) + 1):
                params_with_page = params_with_cat + "&page=%d" % page
                books.update(read_books(params_with_page, get_page(params_with_page)))
                print `n, title, page, cat_total / page_size, len(books), "%.1f%%" % percent(len(books), grand_total)`
            print

    return total, books, cats

def write_books(cur_date, books):
    out = open(out_dir + "/list." + cur_date, 'w')
    for b in books:
        print >> out, b
    out.close()
    return
    i = 0
    error_count = 0

    out = open(out_dir + '/amazon.' + cur_date, 'w')
    index = open(out_dir + '/index.' + cur_date, 'w')

    for asin in books:
        i+= 1
        print i, asin
        for attempt in range(5):
            try:
                page = urlopen('http://amazon.com/dp/' + asin).read()
                if re_expect_end.search(page):
                    break
                print 'bad page ending'
                error_count += 1
                if error_count == 50:
                    print 'too many bad endings'
                    print 'http://amazon.com/dp/' + asin
                    sys.exit(0)
            except:
                pass
            print 'retry'
            sleep(5)
        print >> index, asin, out.tell(), len(page)
        out.write("%10s,%d:%s" % (asin, len(page), page))
    out.close()
    index.close()

one_day = timedelta(days=1)
cur = date(2010, 01, 17)
while True:
    print cur
    total, books, cats = read_page(cur)
    open(out_dir + '/total.' + str(cur), 'w').write(str(total) + "\n")

    out = open(out_dir + "/cats." + str(cur), 'w')
    for i in cats:
        print >> out, i
    out.close()
    print len(books)
    write_books(str(cur), books)
    cur -= one_day
