from lxml.html import parse, tostring, fromstring
import re, sys, os, socket
from urllib import unquote
from urllib2 import urlopen
from time import sleep
from os.path import exists
from datetime import date, timedelta, datetime
import codecs

# scrap Amazon for book and author data

re_expect_end = re.compile('</div>\n</body>\n</html>[ \n]*$')

# publisher = Big Idea Books & Just Me Music
re_personalized = re.compile('Personalized for (.*) \((Boy|Girl)\)', re.I)

def percent(a, b):
    return float(a * 100.0) / b

class PersonalizedBooks(Exception):
    pass

page_size = 12
max_pages = 100
max_results = page_size * max_pages

# http://www.amazon.com/s/qid=1265761735/ref=sr_nr_n_0/177-5112913-4864616?ie=UTF8&rs=1000&bbn=1000&rnid=1000&rh=i%3Astripbooks%2Cp_n%5Ffeature%5Fbrowse-bin%3A618083011%2Cp%5Fn%5Fdate%3A20090101%2Cn%3A%211000%2Cn%3A1
re_product_title = re.compile('/dp/([^/]*)')
re_result_count = re.compile('Showing (?:[\d,]+ - [\d,]+ of )?([\d,]+) Result')
#re_rh_n = re.compile('rh=n%3A(\d+)%2C')
re_rh_n = re.compile('%2Cn%3A(\d+)')
re_facet_count = re.compile(u'^\xa0\(([\d,]+)\)$')
u'\xa0(8)'

base_url = "http://www.amazon.com/s?ie=UTF8&rh="
rh = 'i:stripbooks,p_n_feature_browse-bin:618083011,p_n_date:'

out_dir = '/0/amazon'
arc_dir = '/0/amazon/arc'

# 4 = Children's Books, 28 = Teens
re_child_book_param = re.compile(',n:(4|28)(?:&page=\d+)?$')

def now():
    return datetime.utcnow().replace(microsecond=0)

max_size = 1024 * 1024 * 1024 * 10 # 10 GB
ip = '207.241.229.141'
content_type_hdr = 'Content-Type: '
re_charset_header = re.compile('; charset=(.+)\r\n')
version_block = '1 0 Open Library\nURL IP-address Archive-date Content-type Archive-length\n'

class Scraper:
    def __init__(self, recording=True):
        self.host = 'www.amazon.com'
        self.sock = socket.create_connection((self.host, 80))
        self.recording = recording
        self.cur_arc = None

    def add_to_arc(self, url, start, content_type, reply):
        d = start.strftime('%Y%m%d%H%M%S')
        if self.cur_arc is None or os.stat(arc_dir + self.cur_arc).st_size > max_size:
            self.cur_arc = now().strftime('%Y%m%d%H%M%S') + '.arc'
            assert not exists(arc_dir + self.cur_arc)
            out = open(arc_dir + self.cur_arc, 'w')
            out.write(' '.join(['filespec://' + self.cur_arc, ip, d, 'text/plain', str(len(version_block))]) + '\n')
            out.write(version_block)
        else:
            out = open(arc_dir + self.cur_arc, 'a')
        out.write('\n' + ' '.join([url, ip, d, content_type, str(len(reply))]) + '\n')
        out.write(reply)
        out.close()

    def get(self, url):
        start = now()
        send = 'GET %s HTTP/1.1\r\nHost: %s\r\nUser-Agent: Mozilla/5.0\r\nAccept-Encoding: identity\r\n\r\n' % (url, self.host)
        self.sock.sendall(send)

        fp = self.sock.makefile('rb', 0)
        recv_buf = ''

        line = fp.readline()
        if not line.startswith('HTTP/1.1 200'):
            print('status:', repr(line))
        recv_buf += line

        body = ''
        content_type = None
        charset = None
        for line in fp: # read headers
            recv_buf += line
            if line.lower().startswith('transfer-encoding'):
                assert line == 'Transfer-Encoding: chunked\r\n'
            if line == '\r\n':
                break
            if line.lower().startswith('content-type'):
                assert line.startswith(content_type_hdr)
                assert line[-2:] == '\r\n'
                content_type = line[len(content_type_hdr):line.find(';') if ';' in line else -2]
                if 'charset' in line.lower():
                    m = re_charset_header.search(line)
                    charset = m.group(1)

        while True:
            line = fp.readline()
            recv_buf += line
            chunk_size = int(line, 16)
            if chunk_size == 0:
                break
            chunk = fp.read(chunk_size)
            recv_buf += chunk
            body += chunk
            assert chunk_size == len(chunk)
            recv_buf += fp.read(2)
        line = fp.readline()
        recv_buf += line
        fp.close()
        if self.recording:
            self.add_to_arc(url, start, content_type, recv_buf)
        return body.decode(charset) if charset else body

scraper = Scraper(recording=True)

def get_url(params):
    url = base_url + params
    page = scraper.get(url)
    return fromstring(page)

def get_total(root):
    if root.find(".//h1[@id='noResultsTitle']") is not None:
        return 0
    result_count = root.find(".//td[@class='resultCount']").text
    m = re_result_count.match(result_count)
    return int(m.group(1).replace(',', ''))

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
    if re_child_book_param.search(params) and all(re_personalized.search(span.text) for span in root.find_class('srTitle')):
        raise PersonalizedBooks
    return [re_product_title.search(a.attrib['href']).group(1) for a in book_links if a is not None and a.text]

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
        if not m1:
            print('no match:')
            print(repr(href))
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

def read_page(params):
    # read search results page
    root = get_url(params)
    total = get_total(root)
    if total == 0:
        print 'no results found'
        return total, set(), []
    grand_total = total
    pages = (total / page_size) + 1
    print 'total:', total, 'pages:', pages

    cats = get_cats(root)
    print 'cats 1'
    for a, b, c in cats:
        print "%8d %-30s %8d" % (a, b, c)
    #return grand_total, [], cats

    books = set()

    books.update(read_books(params, root))
    for page in range(2, min((pages, 100))+1):
        params_with_page = params + "&page=%d" % page
        books.update(read_books(params_with_page, get_url(params_with_page)))
        print page, len(books)

    print len(books)

    cats = get_cats(root)
    print 'cats 2'
    for a, b, c in cats:
        print "%8d %30s %8d" % (a, b, c)
    print 'cat total:', sum(i[2] for i in cats)
    if total > max_results:
        for n, title, count in cats:
            print(repr(n, title, count))
            params_with_cat = params + ",n:" + str(n)
            root = get_url(params_with_cat)
            cat_total = get_total(root)
            pages = (cat_total / page_size) + 1
            print 'cat_total:', total, 'pages:', total / page_size
            if cat_total > max_results:
                print 'cat_total (%d) > max results (%d)' % (total, max_results)
    #        assert cat_total <= max_results
            try:
                books.update(read_books(params_with_cat, root))
            except PersonalizedBooks:
                print 'WARNING: Personalized Books'
                continue
            for page in range(2, min((pages, 100)) + 1):
                params_with_page = params_with_cat + "&page=%d" % page
                try:
                    books.update(read_books(params_with_page, get_url(params_with_page)))
                except PersonalizedBooks:
                    print 'WARNING: Personalized Books'
                    break
                print(repr(n, title, page, cat_total / page_size, len(books), "%.1f%%" % percent(len(books), grand_total)))

    return total, books, cats

def write_books(books):
    i = 0
    error_count = 0

    for asin in books:
        i+= 1
        for attempt in range(5):
            try:
                #page = urlopen('http://amazon.com/dp/' + asin).read()
                page = scraper.get('http://www.amazon.com/dp/' + asin)
                if re_expect_end.search(page):
                    break
                print('bad page ending')
                print(repr(page[-60:]))
                error_count += 1
                if error_count == 50:
                    print 'too many bad endings'
                    print 'http://amazon.com/dp/' + asin
                    sys.exit(0)
            except:
                pass
            print 'retry'
            sleep(5)

if __name__ == '__main__':

    one_day = timedelta(days=1)
    cur = date(2009, 1, 1) # start date
    cur = date(2009, 11, 11) # start date
    #cur = date(2009, 12, 25)
    while True:
        print cur
        total, books, cats = read_page(rh + cur.strftime("%Y%m%d"))
        open(out_dir + '/total.' + str(cur), 'w').write(str(total) + "\n")

        out = open(out_dir + "/cats." + str(cur), 'w')
        for i in cats:
            print >> out, i
        out.close()
        print len(books)
        write_books(books)
        cur += one_day
