from lxml.html import parse, tostring
import re, os, sys, web
from warnings import warn
from math import floor
from pprint import pprint
import htmlentitydefs

class BrokenTitle:
    pass

class IncompletePage:
    pass

role_re = re.compile("^ \(([^)]+)\)")

re_title = re.compile("""
    (?:\ \[([^a-z]+)\]\ )? # flags
    \ 
    \(([^()]+|[^()]*\(.*\)[^()]*)\)
    """, re.MULTILINE | re.X)

re_split_title = re.compile(r'''^
    (.+?(?:\ \(.+\))?)
    (?::\ (\ *[^:]+))?$
''', re.X)

re_list_price = re.compile('^\$([\d,]+)\.(\d\d) $')
re_amazon_price = re.compile('^\$([\d,]+)\.(\d\d)$')
# '$0.04\n      \n    '
re_you_save = re.compile('^\$([\d,]+)\.(\d\d)\s*\((\d+)%\)\s*$')

re_pages = re.compile('^\s*(\d+)(?:\.0)? pages\s*$')
re_sales_rank = re.compile('^ #([0-9,]+) in Books')
re_html_in_title = re.compile('</?(i|em|br)>', re.I)

def unescape(text):
    def fixup(m):
        text = m.group(0)
        if text[:2] == "&#":
            # character reference
            try:
                if text[:3] == "&#x":
                    return unichr(int(text[3:-1], 16))
                else:
                    return unichr(int(text[2:-1]))
            except ValueError:
                pass
        else:
            # named entity
            try:
                text = unichr(htmlentitydefs.name2codepoint[text[1:-1]])
            except KeyError:
                pass
        return text # leave as is
    return re.sub("&#?\w+;", fixup, text)

def to_dict(k, v):
    return {k: v} if v else None

def read_authors(by_span):
    authors = []
    assert by_span.text == '\n\nby '
    expect_end = False
    for e in by_span:
        if expect_end:
            assert e.tag in ('br', 'span')
            break
        assert e.tag == 'a'
        if e.tail.endswith('\n\n'):
            expect_end = True
        else:
            assert e.tail.endswith(', ')
        m = role_re.match(e.tail)
        if m:
            authors.append({ 'name': e.text, 'role': m.group(1) })
        else:
            authors.append({ 'name': e.text })
    return authors

def get_title_and_authors(doc):
    try:
        prodImage = doc.get_element_by_id('prodImage')
    except KeyError:
        raise IncompletePage
    full_title = unescape(prodImage.attrib['alt']) # double quoted
    full_title = re_html_in_title.sub('', full_title).replace('&apos;', "'")

    m = re_split_title.match(full_title)
    (title, subtitle) = m.groups()
    # maybe need to descape title
    title_id = doc.get_element_by_id('btAsinTitle')
    assert title_id.tag == 'span'
    assert title_id.getparent().tag == 'h1'
    assert title_id.getparent().attrib['class'] == 'parseasinTitle'
    buying_div = title_id.getparent().getparent()
    assert buying_div.tag == 'div'
    assert buying_div.attrib['class'] == 'buying'
    by_span = buying_div[1]
    assert by_span.tag == 'span'

    book = {
        'full_title': full_title,
        'title': title,
        'has_cover_img': "no-image-avail" not in prodImage.attrib['src']
    }

    authors = []
    if len(by_span) and by_span[0].tag == 'a':
        #print len(by_span), [e.tag for e in by_span]
        book['authors'] = read_authors(by_span)
    title_text = title_id.text_content()
    if not title_text.startswith(full_title):
        print 'alt:', `prodImage.attrib['alt']`
        print 'title mistmach:', `full_title`, '!=', `title_text`
        raise BrokenTitle
    btAsinTitle = title_text[len(full_title):]
    m = re_title.match(btAsinTitle)
    (flag, book['binding']) = m.groups()
    if flag:
        book['flag'] = flag
    if subtitle:
        book['subtitle'] = subtitle

    return book

def dollars_and_cents(dollars, cents):
    # input: dollars and cents as strings
    # output: value in cents as an int
    return int(dollars.replace(',', '')) * 100 + int(cents)

def read_price_block(doc):
    price_block = doc.get_element_by_id('priceBlock', None)
    book = {}
    if price_block is None:
        return
    assert price_block.tag == 'div' and price_block.attrib['class'] == 'buying'
    table = price_block[0]
    assert table.tag == 'table' and table.attrib['class'] == 'product'
    for tr in table:
        assert tr.tag == 'tr' and len(tr) == 2
        assert all(td.tag == 'td' for td in tr)
        heading = tr[0].text
        value = tr[1].text

        if heading == 'List Price:':
            m = re_list_price.match(tr[1].text)
            list_price = dollars_and_cents(m.group(1), m.group(2))
            book["list_price"] = list_price
        elif heading == "Price:":
            b = tr[1][0]
            assert b.tag == 'b' and b.attrib['class'] == 'priceLarge'
            m = re_amazon_price.match(b.text)
            amazon_price = dollars_and_cents(m.group(1), m.group(2))
            book["amazon_price"] = amazon_price
        elif heading == 'You Save:':
            continue # don't need to check
            # fails for 057124954X: '$0.04\n      \n    '
            m = re_you_save.match(value)
            you_save = dollars_and_cents(m.group(1), m.group(2))
            assert list_price - amazon_price == you_save
            assert floor(float(you_save * 100) / list_price + 0.5) == int(m.group(3))
        elif heading == 'Value Priced at:':
            continue # skip
            m = re_amazon_price.match(value)
            book["value_priced_at"] = dollars_and_cents(m.group(1), m.group(2))
        elif heading == 'Import List Price:':
            pass

    return book

def find_avail_span(doc):
    for div in doc.find_class('buying'):
        if div.tag != 'div' or not len(div):
            continue
        if div[0].tag == 'span':
            span = div[0]
        elif div[0].tag == 'br' and div[1].tag == 'b' and div[2].tag == 'span':
            span = div[2]
        else:
            continue
        if span.attrib['class'].startswith('avail'):
            return span

def read_avail(doc):
    traffic_signals = set(['Red', 'Orange', 'Green'])
    span = find_avail_span(doc)
    color = span.attrib['class'][5:]
    assert color in traffic_signals
    gift_wrap = span.getnext().getnext().tail
    book = {
        'avail_color': color,
        'amazon_availability': span.text,
        'gift_wrap': bool(gift_wrap) and 'Gift-wrap available' in gift_wrap
    }
    return book

def read_other_editions(doc):
    oe = doc.get_element_by_id('oeTable', None)
    if oe is None:
        return
    assert oe.tag == 'table' and oe.attrib['class'] == 'otherEditions'
    assert len(oe) == 2 and len(oe[0]) == 2 and len(oe[1]) == 2
    assert oe[0][0][0].tag == 'a'
    oe = oe[0][0][1]
    assert oe.tag == 'table'
    other_editions = []
    for tr in oe[1:]:
        assert tr.tag == 'tr'
        if 'bgcolor' in tr.attrib:
            assert tr.attrib['bgcolor'] == '#ffffff'
        else:
            assert tr[0].attrib['id'] == 'oeShowMore'
            break
        assert tr[0].attrib['class'] == 'tiny'
        a = tr[0][0]
        assert a.tag == 'a'
        row = [a.attrib['href'][-10:], a.text, a.tail.strip()]
        other_editions.append(row)
    return {'other_editions': other_editions }

def read_sims(doc):
    sims = doc.find_class('sims-faceouts')
    if len(sims) == 0:
        return
    assert len(sims) == 1
    sims = sims[0]
    assert sims.tag == 'table'
    found = []
    if sims[0].tag == 'tbody':
        tr = sims[0][0]
    else:
        assert sims[0].tag == 'tr'
        tr = sims[0]
    for td in tr:
        assert td.tag == 'td'
        a = td[1][0]
        assert a.tag == 'a'
        found.append({'asin': a.attrib['href'][-10:], 'title': a.text})
    return to_dict('sims', found)

def find_product_details_ul(doc):
    a = doc.get_element_by_id('productDetails', None)
    if a is None:
        return
    try:
        assert a.tag == 'a' and a.attrib['name'] == 'productDetails'
    except:
        print tostring(a)
        raise
    hr = a.getnext()
    assert hr.tag == 'hr' and hr.attrib['class'] == 'bucketDivider'
    table = hr.getnext()
    td = table[0][0]
    assert td.tag == 'td' and td.attrib['class'] == 'bucket'
    h2 = td[0]
    assert h2.tag == 'h2' and h2.text == 'Product Details'
    div = td[1]
    assert div.tag == 'div' and div.attrib['class'] == 'content'
    ul = div[0]
    if div[0].tag == 'table':
        ul = div[1]
    assert ul.tag == 'ul'
    assert ul[-1].tag == 'div' and ul[-2].tag == 'p'
    return ul

def read_li(li):
    assert li.tag == 'li'
    b = li[0]
    assert b.tag == 'b'
    return b

re_series = re.compile('^<li>(?:This is item <b>(\d+)</b> in|This item is part of) <a href="?/gp/series/(\d+).*?><b>The <i>(.+?)</i> Series</b></a>\.</li>')

def read_series(doc):
    ul = doc.find_class('linkBullets')
    if len(ul) == 0:
        return
    assert len(ul) == 1
    ul = ul[0]
    if len(ul) == 0:
        return
    li = ul[0]
    assert li.tag == 'li'
    (series_num, series_id, series) = re_series.match(tostring(li)).groups()
    found = {}
    if series_num:
        found["series_num"] = int(series_num)
    found["series"] = series
    found["series_id"] = series_id
    return found

def read_product_details(doc):
    ul = find_product_details_ul(doc)
    if ul is None:
        return

    headings = {
        'Publisher': 'publisher',
        'Language': 'language',
        'ISBN-10': 'isbn_10',
        'ISBN-13': 'isbn_13',
        'ASIN': 'asin',
        'Product Dimensions': 'dimensions',
        'Shipping Weight': 'shipping_weight',
    }

    found = {}
    ul_start = 0
    if 'Reading level' in ul[0][0].text:
        ul_start = 1
        li = ul[0]
        b = read_li(li)
        found['reading_level'] = b.tail.strip()

    li = ul[ul_start]
    b = read_li(li)
    (binding, pages) = (b.text, b.tail)
    if pages:
        m = re_pages.match(pages)
        if m:
            found['number_of_pages'] = int(m.group(1))
        else:
            warn("can't parse number_of_pages: " + pages)

    seen_average_customer_review = False
    for li in ul[ul_start + 1:-2 if ul[-3].tag != 'br' else -3]:
#        if li.tag == 'p' and len(li) == 0:
#            continue
        b = read_li(li)
        h = b.text.strip(': \n')
        if h in ('Also Available in', 'In-Print Editions'):
            break
        if seen_average_customer_review:
            break
        if h == 'Amazon.com Sales Rank':
            m = re_sales_rank.match(b.tail)
            found['sales_rank'] = int(m.group(1).replace(",", ""))
            break
        if h in ('Shipping Information', 'Note', 'Shipping'):
            continue
        if h == 'Average Customer Review':
            seen_average_customer_review = True
            continue
        if h == 'Shipping Weight':
            found['shipping_weight'] = b.tail.strip('( ')
            continue
        heading = headings[h]
        found[heading] = b.tail.strip()
    return found

re_pub_date = re.compile("^(.*) \((.*\d{4})\)$")
re_pub_edition = re.compile("^(.*); (.*)$")

def parse_publisher(edition):
    if 'publisher' in edition:
        m = re_pub_date.match(edition["publisher"])
        if m:
            edition["publisher"] = m.group(1)
            edition["publish_date"] = m.group(2)
        m = re_pub_edition.match(edition["publisher"])
        if m:
            edition["publisher"] = m.group(1)
            edition["edition"] = m.group(2)

re_latest_blog_posts = re.compile('\s*(.*?) latest blog posts')
re_plog_link = re.compile('^/gp/blog/([A-Z0-9]+)$')

def read_plog(doc):
    div = doc.get_element_by_id('plog', None)
    if div is None:
        return
    assert div.tag == 'div' and div.attrib['class'] == 'plog'
    table = div[1]
    b = table[0][0][0]
    assert b.tag == 'b' and b.attrib['class'] == 'h1'
    m = re_latest_blog_posts.match(b.text)
    name = m.group(1)
    found = {}
    if name.endswith("'s"):
        found["plog_name"] = name[:-2]
    else:
        assert name.endswith("s'")
        found["plog_name"] = name[:-1]
    div = table[2][1][0]
    found["plog_img"] = div[0].attrib['src'].replace(".T.", ".L.")
    ul = div[-1]
    assert ul.tag == 'ul' and ul.attrib['class'] == 'profileLink'
    li = ul[0]
    assert li.tag == 'li' and li.attrib['class'] == 'carat'
    assert li[0].tag == 'a'

    href = li[0].attrib['href']
    m = re_plog_link.match(href)
    found["plog_id"] = m.group(1)

    return found

re_cite = {
    'citing': re.compile('\nThis book cites (\d+) \nbook(?:s)?:'),
    'cited': re.compile('\n(\d+) \nbook(?:s)? \ncites? this book:')
}
    
def read_citing(doc):
    div = doc.get_element_by_id('bookCitations', None)
    found = {}
    if div is None:
        return
    content = div[0][2]
    assert content.tag == 'div' and content.attrib['class'] == 'content'
    a = content[0]
    assert a.tag == 'a'
    b = content[1]
    name = a.attrib['name']
    assert name in ('citing', 'cited')
    found[name] = b.text
    if len(content) > 7:
        print len(content)
        for num, i in enumerate(content):
            print num, i.tag, i.attrib
        a = content[8]
        assert a.tag == 'a'
        b = content[9]
        assert a.attrib['name'] == 'cited'
        found['cited'] = b.text
    for k, v in found.items():
        m = re_cite[k].match(v)
        found[k] = int(m.group(1))
    return found

def find_inside_this_book(doc):
    for b in doc.find_class('h1'):
        if b.text == 'Inside This Book':
            assert b.tag == 'b'
            return b.getparent()
    return None

def read_first_sentence(inside):
    if len(inside) == 4:
        assert inside[2].tag == 'span'
        assert inside[2].attrib['class'] == 'tiny'
        assert inside[2][0].tail.strip() == 'Browse and search another edition of this book.'
        div = inside[3]
    else:
        assert len(inside) == 3
        div = inside[2]
    assert div.tag == 'div' and div.attrib['class'] == 'content'
    if div[0].tag in ('a', 'b'):
        assert div[0].text != 'First Sentence:'
        return
    assert div[0].tag == 'strong'
    assert div[0].text == 'First Sentence:'
    assert div[1].tag == 'br'
    return div[1].tail.strip(u"\n \xa0")

def find_bucket(doc, text):
    for div in doc.find_class('bucket'):
        h2 = div[0]
        if h2.tag == 'h2' and h2.text == text:
            return div
    return None

# New & Used Textbooks

def read_subject(doc):
    div = find_bucket(doc, 'Look for Similar Items by Subject')
    if div is None:
        return
    assert div.tag == 'div'
    form = div[1][0]
    assert form.tag == 'form'
    input = form[0]
    assert input.tag == 'input' and input.attrib['type'] == 'hidden' \
        and input.attrib['name'] == 'index' \
        and input.attrib['value'] == 'books'
    found = []
    for input in form[1:-4:3]:
        a = input.getnext()
        assert a.tag == 'a'
        found_text = a.text if len(a) == 0 else a[0].text
        assert found_text is not None
        found.append(found_text)
    return to_dict('subjects', found)

def read_category(doc):
    div = find_bucket(doc, 'Look for Similar Items by Category')
    if div is None:
        return
    assert div.tag == 'div'
    ul = div[1][0]
    assert ul.tag == 'ul'
    found = []
    for li in ul:
        assert all(a.tail == ' > ' for a in li[:-1])
        cat = [a.text for a in li]
        if cat[-1] == 'All Titles':
            cat.pop()
        found.append(tuple(cat))
#        if 'Series' in cat:
#            edition["series2"] = cat
    # maybe strip 'Books' from start of category
    found = [i[1:] if i[0] == 'Books' else i for i in found]
    return to_dict('category', found)

def read_tags(doc):
    table = doc.find_class('tag-cols')
    if len(table) == 0:
        return
    assert len(table) == 1
    table = table[0]
    assert len(table) == 1
    tr = table[0]

def read_edition(doc):
    edition = {}
    book = get_title_and_authors(doc)
    edition.update(book)

    ret = read_price_block(doc)
    if ret:
        edition.update(ret)
    inside = find_inside_this_book(doc)
    if inside is not None:
        sentence = read_first_sentence(inside)
        if sentence:
            edition['first_sentence'] = sentence
    func = [
        #read_citing,
        read_plog,
        read_series,
        #read_avail,
        read_product_details,
        read_other_editions,
        read_sims,
        read_subject,
        read_category,
    ]
    for f in func:
        ret = f(doc)
        if ret:
            edition.update(ret)
    parse_publisher(edition)
    if 'isbn_10' not in edition and 'asin' not in edition:
        return None
    return edition

# ['subtitle', 'binding', 'shipping_weight', 'category', 'first_sentence',  'title', 'full_title', 'authors', 'dimensions', 'publisher', 'language', 'number_of_pages', 'isbn_13', 'isbn_10', 'publish_date']
def edition_to_ol(edition):
    ol = {}
    fields = ['title', 'subtitle', 'publish_date', 'number_of_pages', 'first_sentence']
    for f in fields:
        if f in edition:
            ol[f] = edition[f]
    if 'isbn_10' in edition:
        ol['isbn_10'] = [edition['isbn_10']]
    if 'isbn_13' in edition:
        ol['isbn_13'] = [edition['isbn_13'].replace('-','')]
    if 'category' in edition:
        ol['subjects'] = [' -- '.join(i) for i in edition['category']]
    if 'binding' in edition:
        ol['physical_format'] = edition['binding']
    if 'dimensions' in edition:
        ol['physical_dimensions'] = edition['dimensions']
    if 'shipping_weight' in edition:
        ol['weight'] = edition['shipping_weight']
    if 'authors' in edition:
        ol['authors'] = edition['authors']

    for k, v in ol.iteritems():
        if isinstance(v, basestring) and v[-1] == '(':
            pprint(ol)
            print 'ends with "(":', `k, v`
            sys.exit(0)

    return ol

if __name__ == '__main__':
    #for dir in ('/2008/sample/', 'pages/'):
    page_dir = sys.argv[1]
    for filename in os.listdir(page_dir):
        #if '1435438671' not in filename:
        #    continue
        if filename.endswith('.swp'):
            continue
        edition = {}
        doc = parse(page_dir + '/' + filename).getroot()
        assert doc is not None
        edition = read_edition(doc)
        ol = edition_to_ol(edition)
        pprint (ol)
