import re, sys
from warnings import warn
from math import floor

re_product_description = re.compile("""
    <hr\ noshade="true"\ size="1"\ class="bucketDivider"\ />\s+
    <div\ class="bucket"\ id="productDescription">\s+
    <b\ class="h1">Editorial\ Reviews</b><br\ />\s+
    .*?
    <b>From\ the\ Publisher</b><br\ />\s+
    (.*?)\s+
    (?:<a\ href=".*?">See\ all\ Editorial\ Reviews</a>)?
    </div>
#""", re.DOTALL | re.X)

sales_rank_re = re.compile('^#([0-9,]+) in Books(?:.*<table .*?>(.*)</table>)?')
reading_level_re = re.compile('^(.*)<br />$')
pages_re = re.compile('^(\d+)(?:\.0)? pages$')
shipping_weight_re = re.compile('^(\d+(?:\.\d)? (?:pounds|ounces))(?: \(<a href="[^"]+">View shipping rates and policies</a>\))?$')
pub_date_re = re.compile("^(.*) \((.*\d{4})\)$")
pub_edition_re = re.compile("^(.*); (.*)$")

re_tag_cols = re.compile('''<table class="tag-cols"(.*?)</table>''', re.DOTALL)

re_tag_row = re.compile('<div class="tag-row" tag="([^"]*?)">')

def parse_tags(m, edition):
    edition["tags"] = re_tag_row.findall(m.group(1))

re_plog = re.compile(r'''(<div\ id="plog"\ class="plog">\s*.*?</li>)''', re.DOTALL)
re_plog2 = re.compile(r'''
<div\ id="plog"\ class="plog">\s*
<hr\ noshade="noshade"\ size="1"\ class="bucketDivider"\ style=".*?
<b\ class="h1">\s*(.*?)\ latest\ blog\ posts\s*</b>.*?
<div\ class="plogLeftCol">\s*
<img\ src="(.*?)".*?>.*
<ul\ class="profileLink">\s*
<li\ class="carat">
<a\ href="/gp/blog/(.*)">\1\ Blog</a></li>
''', re.DOTALL | re.X)

def parse_plog(m, edition):
    m = re_plog2.search(m.group(1))
    assert m
    plog_name = m.group(1)
    if plog_name.endswith("'s"):
        edition["plog_name"] = plog_name[:len(plog_name)-2]
    else:
        assert plog_name.endswith("s'")
        edition["plog_name"] = plog_name[:len(plog_name)-1]
    edition["plog_img"] = m.group(2).replace(".T.", ".L.")
    edition["plog_id"] = m.group(3)

re_citing0 = re.compile("<a name='citing' >(.*?)</div></div></div>", re.DOTALL)

re_citing = re.compile('''<a name='citing' ></a><b>
This book cites (\d+)\s*
books?:\s*
</b><br /><ul style="margin-bottom: 20px;">(?:(.*?)<div class="spacer">&nbsp;</div>
<a name='cited' ></a><b>
(\d+)\s*\n(?:books\s*\ncite this book|book\s*\ncites this book:)
</b><br /><ul style="margin-bottom: 20px;">(.*?)</ul>.*?)?</div></div></div>''', re.DOTALL)

re_citing = re.compile('''<a name='citing' ></a><b>
This book cites (\d+)\s*
books?:\s*
</b><br /><ul style="margin-bottom: 20px;">(.*?)<div class="spacer">&nbsp;</div>''', re.DOTALL)

re_citing_li = re.compile('<li>\s*(.*?)\s*</li>', re.DOTALL)
re_citing_li2 = re.compile('^<a href="http://.*?/dp/([0-9A-Z]{10})">(.*?)</a>\s*by (.*?)\s*(?:on|in)\s*(.*)$', re.DOTALL)

re_page_list = re.compile('<a href=".*?">(.*?)</a>')

def parse_citing_li(html):
    for m in re_citing_li.finditer(html): 
        if not m.group(1).startswith('<'): # empty cite
            continue
        m = re_citing_li2.match(m.group(1))
        print m.groups()
        print re_page_list.findall(m.group(4))

def parse_citing(html, edition):
    if html.find("<a name='citing' >") == -1:
        return
    m = re_citing0.search(html)
    print m.group(1)
    m = re_citing.search(html)
    (this_cites_count, this_cites, cite_this_count, cite_this) = m.groups()
#    print this_cites_count, cite_this_count
    parse_citing_li(this_cites)
    parse_citing_li(cite_this)
    return
    for m in re_citing_li.finditer(m.group(1)): 
        if m.group(1).startswith('on'): # empty cite
            continue
        print m.group(1)
        m = re_citing_li2.match(m.group(1))
        assert m
        print m.groups()
        print re_page_list.findall(m.group(4))

re_price_block = re.compile('<div class="buying" id="priceBlock">\s*(.*?)\s*</div>',re.DOTALL)
re_price_block_table = re.compile('<table class="product">\s*(.*)\s*</table>',re.DOTALL)
re_price_block_tr = re.compile('<tr>\s*(.*?)\s*</tr>', re.DOTALL)
re_price_block_tr2 = re.compile('<td class="productLabel">(.*?)</td>\s*(<td.*?</td>)', re.DOTALL)

re_list_price = re.compile('<td(?: class="listprice")?>\$([\d,]+)\.(\d\d) </td>')
re_amazon_price = re.compile('<td><b class="price">\$([\d,]+)\.(\d\d)</b>')
re_you_save = re.compile('<td class="price">\$([\d,]+)\.(\d\d)\s*\((\d+)%\)\s*</td>')

def dollars_and_cents(dollars, cents):
    # input: dollars and cents as strings
    # output: value in cents as an int
    return int(dollars.replace(',', '')) * 100 + int(cents)

def parse_price_block(m, edition):
    m = re_price_block_table.search(m.group(1))
    for m in re_price_block_tr.finditer(m.group(1)):
        if m.group(1).startswith('<td></td>'):
            continue
        m = re_price_block_tr2.match(m.group(1))
        (heading, value) = m.groups()
        if heading == 'List Price:':
            m = re_list_price.match(value)
            list_price = dollars_and_cents(m.group(1), m.group(2))
            edition["list_price"] = list_price
        elif heading == "Price:":
            m = re_amazon_price.match(value)
            amazon_price = dollars_and_cents(m.group(1), m.group(2))
            edition["amazon_price"] = amazon_price
        elif heading == 'You Save:':
            m = re_you_save.match(value)
            you_save = dollars_and_cents(m.group(1), m.group(2))
            assert list_price - amazon_price == you_save
            assert floor(float(you_save * 100) / list_price + 0.5) == int(m.group(3))
        elif heading == 'Value Priced at:':
            m = re_amazon_price.match(value)
            edition["value_priced_at"] = dollars_and_cents(m.group(1), m.group(2))
        elif heading == 'Import List Price:':
            pass

#    print edition

re_used_and_new = re.compile('<div class="buying" id="primaryUsedAndNew">\s*(.*?)\s*</div>', re.DOTALL)

re_used_and_new2 = re.compile('<a href="(?:.*?)" class="buyAction">\n(\d+) used & new</a> available from <span class="price">\$([\d,]+)\.(\d\d)</span><br />');

def parse_used_and_new(m, edition):
    if m.group(1) == '':
        return

    m = re_used_and_new2.match(m.group(1))
    edition["new_and_used_count"] = int(m.group(1))
    edition["new_and_used_price"] = dollars_and_cents(m.group(2), m.group(3))

re_other_editions = re.compile('<table border="0" cellspacing="0" cellpadding="0" class="otherEditions">\s*(.*?)\s*</table>', re.DOTALL)

re_other_editions_tr = re.compile('<tr bgcolor= #ffffff >\s*(.*?)\s*</tr>', re.DOTALL)
re_other_editions_see_all = re.compile('See all (\d+) editions and formats')
re_other_editions2 = re.compile('^<td  class="tiny"  >\s*<a href="http://www.amazon.com(?::80.*?|(?:/.*?/dp/|/gp/product/)([0-9A-Z]{10}).*?)">(.*?)</a>\s*(?:\((.*?)\))?\s*</td>')
re_other_edition_url = re.compile('/dp/(\d{9}[\dX])')
re_other_edition_empty = re.compile('<td\s*class="tiny"\s*>\s*</td>\s*<td\s*class="tiny"\s*>\s*</td>\s*<td class="tinyprice"></td>')

def parse_other_editions(m, edition):
    m2 = re_other_editions_see_all.search(m.group(1))
    if m2:
        other_edition_count = int(m2.group(1))
        assert other_edition_count > 4
        edition['other_edition_count'] = other_edition_count

    other_editions = []
    for m in re_other_editions_tr.finditer(m.group(1)):
        if re_other_edition_empty.match(m.group(1)):
            continue
        m = re_other_editions2.match(m.group(1))
        other_editions.append(m.groups())
    if other_editions:
        edition['other_editions'] = other_editions

def parse_title(html, edition, prev_end):
    # parse title
    expect_div_title_str = '<div class="buying"><b class="sans">' + edition["title"]
    if 'subtitle' in edition:
        expect_div_title_str += ': ' + edition['subtitle']
    pos = html[prev_end:].find(expect_div_title_str)
    assert pos != -1
    return pos + prev_end + len(expect_div_title_str)

re_div_title = re.compile("""
    (?:\ \[([^a-z]+)\]\ )? # flags
    \ 
    \(([^()]+|[^()]*\(.*\)[^()]*)\) # binding
    (?:\ ?<!--aoeui-->|\ )?
    </b><br\ />
    (.*?) # authors
    (?:<br\ />)?
    (?:<span\ class="tiny">)?$""", re.MULTILINE | re.X)

author_re = re.compile('<a href="(?:[^"]*)">(.*?)</a>(?: \(([^)]+)\))?')

def parse_div_title(html, edition, prev_end):
    m = re_div_title.match(html, prev_end)
    assert prev_end < m.pos + m.end()
    
    (flag, binding, authors) = m.groups()
    if flag:
        edition['flag'] = flag
    edition['binding'] = binding
    if authors:
        assert authors.startswith("by ")
        author_names = author_re.findall(authors[3:])

        expect_author = ','.join([x[0].replace('\\', '') for x in author_names])
        assert edition['desc_author'] == expect_author
        edition['authors'] = [x for x in author_names if x != '']
    else:
        assert not edition['desc_author']
    del edition['desc_author']
    return m.end()

#re_pop_cat_row = re.compile('<tr valign="top"><td align="right"><nobr>#(\d+) in </nobr></td><td align="left">&nbsp;<a href="/gp/bestsellers/books">Books</a>( &gt; <a href="/gp/bestsellers/books/\d+">(.*)</a>)+ <b><a href="/gp/bestsellers/books/\d+">(.+)</a></b></td></tr>')
re_pop_cat_row = re.compile('<tr valign="top"><td align="right"><nobr>#(\d+) in </nobr></td><td align="left">&nbsp;<a href="/gp/bestsellers/(.*?)">(.*?)</a>((?: &gt; <a href="/gp/bestsellers/books/\d+">.*?</a>)*) &gt; <b><a href="/gp/bestsellers/books/\d+">(.+?)</a></b></td></tr>')
re_pop_cat2 = re.compile(' &gt; <a href="/gp/bestsellers/books/\d+">(.*?)</a>')

def popular_cat(html):
    pop = []
    for m in re_pop_cat_row.finditer(html):
        assert m.group(2) == 'books'
        assert m.group(3) == 'Books'
        cat = [x.group(1) for x in re_pop_cat2.finditer(m.group(4))]
        cat.append(m.group(5))
        pop.append({ 'num': int(m.group(1)), 'cat': cat })
    return pop

re_product_details = re.compile("""
    ^<a\ name="productDetails"\ id="productDetails"></a>.*?
    <b\ class="h1">Product\ Details</b><br\ />\s+
    <div\ class="content">\s+(.+?)</ul>""", re.MULTILINE | re.DOTALL | re.X)
    
def parse_details(m, edition):
    details = li_re.findall(m.group(1))
    if details[0][0] == "Reading level":
        edition["reading_level"] = reading_level_re.match(details.pop(0)[1]).group(1)
    (binding2, pages) = details.pop(0)
    if edition["binding"] != binding2:
        warn("binding mismatch: " + edition["binding"] + " != " + binding2)
    if pages:
        m = pages_re.match(pages)
        if m:
            edition['number_of_pages'] = int(m.group(1))
        else:
            warn("can't parse number_of_pages: " + pages)

    headings = {
        'Publisher': 'publisher',
        'Language': 'language',
        'ISBN-10': 'isbn_10',
        'ISBN-13': 'isbn_13',
        'ASIN': 'asin',
        'Product Dimensions': 'dimensions',
        'Shipping Weight': 'shipping_weight',
    }

    seen_average_customer_review = 0
    for (h, v) in details:
#        if h in 'Also Available in':
#            parse_aai(v, edition)
        if h in ('Also Available in', 'In-Print Editions'):
#            print v
            break
        if seen_average_customer_review:
            break
        if h == 'Amazon.com Sales Rank':
            m = sales_rank_re.match(v)
            edition['sales_rank'] = int(m.group(1).replace(",", ""))
            if m.group(2):
                edition['popular_cat'] = popular_cat(m.group(2))
            break
        if h in ('Shipping Information', 'Note', 'Shipping'):
            continue
        if h == 'Average Customer Review':
            seen_average_customer_review = 1
            continue
        if h == 'Shipping Weight':
            v = shipping_weight_re.match(v).group(1)
        heading = headings[h]
        edition[heading] = v
    parse_publisher(edition)

def parse_publisher(edition):
    if 'publisher' in edition:
        m = pub_date_re.match(edition["publisher"])
        if m:
            edition["publisher"] = m.group(1)
            edition["publish_date"] = m.group(2)
        m = pub_edition_re.match(edition["publisher"])
        if m:
            edition["publisher"] = m.group(1)
            edition["edition"] = m.group(2)

re_inside_this_book = re.compile('<b class="h1">Inside This Book</b>.*?<strong>First Sentence:</strong><br />\s*(.+?)&nbsp;<a href="[^"]+">Read the first page</a>.*?', re.DOTALL)
re_sip = re.compile('<a name="sipbody"><strong>Key Phrases - Statistically Improbable Phrases \(SIPs\):</strong></a>.*?<br />\s*(.+?)<div class="spacer"></div>\s*', re.DOTALL)
re_cap = re.compile('<a name="capbody"><strong>Key Phrases - Capitalized Phrases \(CAPs\):</strong></a>.*?<br />\s*(.+?)<div class="spacer"></div>\s*', re.DOTALL)

def parse_inside_this_book(m, edition):
    edition["first_sentence"] = m.group(1)

re_category = re.compile("""
    ^<div\ class="bucket">\s+
    <b\ class="h1">Look\ for\ Similar\ Items\ by\ Category</b><br\ />\s+
    <div\ class="content">\s+<ul>\s+(.*?)\s*</ul>""", re.MULTILINE | re.DOTALL | re.X)
re_category_li = re.compile('<li>(.+?)</li>', re.MULTILINE | re.DOTALL)

re_link = re.compile('<a href="http://www.amazon.com/.*">(.*)</a>')
re_phrase_link = re.compile('\s*<a href="/phrase/.*" >(.*)</a>')

def parse_category(m, edition):
    category = []
    for x in re_category_li.findall(m.group(1)):
        cat = [re_link.match(y).group(1) for y in x.split(' &gt; ')]
        if cat[0] == 'Amazon Upgrade':
            continue
        if cat[-1] == 'All Titles':
            cat.pop()
        category.append(tuple(cat))
        e = [c for c in cat]
        if 'Series' in e:
            edition["series2"] = e

    edition["category"] = category

re_subject = re.compile("""
    <div\ class="bucket">\s+
    <b\ class="h1">Look\ for\ Similar\ Items\ by\ Subject</b>\s+
    <div\ class="content">\s+(.*?)\s*</div>""", re.X | re.MULTILINE | re.DOTALL)
re_subject_item = re.compile("""
    <input\ type="checkbox"\ name="field\+keywords"\ value="(?:.*)"\ />\ 
    <a\ href="(?:.*)">(.*)</a><br\ />""", re.X)

def parse_subject(m, edition):
    edition["subject"] = [x for x in re_subject_item.findall(m.group(1))]

trans = { 'amp': '&', 'lt': '<', 'gt': '>', 'quot': '"', }
re_html_entity = re.compile('&(amp|lt|gt|quot);')

re_div_class_buying = re.compile('<div class="buying">.*?<b>Availability:</b>\s*(.*?)\s*(?:<br /><br />)?</div>', re.DOTALL)

def parse_avail(m, edition):
    avail = m.group(1)
    edition['gift_wrap'] = avail.endswith(" Gift-wrap available.")
    edition['amazon_availability'] = avail[0:avail.find('.')]

re_title = re.compile("<title>(.*)</title>", re.S)
re_meta_desc = re.compile('<meta name="description" content="Amazon.com: (.*?)" />', re.S)
re_meta_desc2 = re.compile(r"""
    (.+?(?:\ \(.+\))?)
    (?::\ (\ *[^:]+))?
    :\ (Books|Video|DVD|Music)
    (?::\ (.*)\ by\ \4)?$
""", re.X)

def parse_head(html, edition):
    m = re_title.search(html)
    html_title = m.group(1)
    if html_title == "404 - Document Not Found":
        warn("404: " + html_title)
        return
    if html_title.startswith("Amazon.com: :"):
        warn("no title: " + html_title)
        return
    m = re_meta_desc.search(html)
    assert m
    prev_end = m.end()
    description = re_html_entity.sub(lambda m: trans[m.group(1)], m.group(1))
    if description.find(": Book") == -1:
        return
    m = re_meta_desc2.match(description)
    try:
        assert m
    except AssertionError:
        raise
    (title, subtitle, product_type, desc_author) = m.groups()

    check_title(html_title, title, subtitle, product_type, desc_author)

    if product_type != 'Books':
        warn("can't handle type: '" + product_type + "': " + title)
        return
    if title == '':
        warn("empty title: " + html_title)
        return

    edition['title'] = title
    edition['desc_author'] = desc_author

    if subtitle:
        edition['subtitle'] = subtitle
    return prev_end

def check_title(html_title, title, subtitle, product_type, desc_author):
    expect_title = ["Amazon.com", title]
    if subtitle:
        expect_title.append(subtitle)
    expect_title.append(product_type)
    if desc_author:
        expect_title.append(desc_author)
    try:
        assert html_title == ': '.join(expect_title)
    except AssertionError:
        raise

re_prod_image = re.compile('<td id="prodImageCell" .*<img.*src="(.*?)" id="prodImage"')

def parse_prod_image(html, edition, prev_end):
    m = re_prod_image.search(html, prev_end)
    edition["has_cover_img"] = m.group(1).find("no-image-avail") == -1
    return m.end()

re_series = re.compile('^<ul class="linkBullets">\s*(.*?)\s*</ul>$', re.MULTILINE | re.DOTALL)
li_re = re.compile('^<li(?: id="SalesRank")?>\n?<b>\s*(.+?):?\s*</b>\s*(.*?)\s*</li>', re.MULTILINE | re.DOTALL)
re_series2 = re.compile('^<li>(?:This is item <b>(\d+)</b> in|This item is part of) <a href=/gp/series/(\d+).*?><b>The <i>(.+?)</i> Series</b></a>\.</li>$')

def parse_series(m, edition):
    if not m.group(1):
        return
    (series_num, series_id, series) = re_series2.match(m.group(1)).groups()
    if series_num:
        edition["series_num"] = int(series_num)
    edition["series"] = series
    edition["series_id"] = series_id

def parse_product_description(html, edition, prev_end):
    m = re_product_description.search(html)
    if m:
        print filename
        print m.group(1)

def parse_phrase(m):
    phrases = m.group(1).split(', ')
    if phrases[0][0] != '<':
        for p in phrases[1:]:
            assert p[0] != '<'
        return phrases
    return [re_phrase_link.match(p).group(1).replace('&nbsp;', ' ') for p in phrases]

def parse_sip(m, edition):
    edition['sip'] = parse_phrase(m)

def parse_cap(m, edition):
    edition['cap'] = parse_phrase(m)

citing_re = re.compile("<a href='#citing'>This book cites (\d+) book(?:s)?</a>")

def parse_cite_this(m, edition):
    edition["cite_this"] = m.group(1)

cited_re = re.compile("<a href='#cited'>(\d+) book(?:s)? that cite this book")

def parse_this_cites(m, edition):
    edition["this_cites"] = m.group(1)

re_sim = re.compile('^<table class="sims-faceouts"> <tr>\n( *<td.*?</td>\n)</tr>', re.MULTILINE | re.DOTALL)
re_sim2 = re.compile('<td valign="top" width="20%" id="sims.purchase.(?P<isbn>\d{9}[0-9X])">.*?<a href="http://www.amazon.com/[^"]*?">(?P<title>[^<].+?)</a>', re.MULTILINE | re.DOTALL)

def parse_sim(m, edition):
    edition["related"] = [m.groupdict() for m in re_sim2.finditer(m.group(1))]

def parse_sections(html, edition, prev_end):
    sections = [
        ('price_block',     parse_price_block,     re_price_block,     0),
        ('avail',           parse_avail,           re_div_class_buying,1),
        ('used_and_new',    parse_used_and_new,    re_used_and_new,    0),
        ('other_editions',  parse_other_editions,  re_other_editions,  0),
        ('sim',             parse_sim,             re_sim,             0),
        ('details',         parse_details,         re_product_details, 1),
        ('series',          parse_series,          re_series,          1),
        ('plog',            parse_plog,            re_plog,            0),
        ('cite_this',       parse_cite_this,       citing_re,          0),
        ('this_cites',      parse_this_cites,      cited_re,           0),
        ('inside_this_book',parse_inside_this_book,re_inside_this_book,0),
        ('sip',             parse_sip,             re_sip,             0),
        ('cap',             parse_cap,             re_cap,             0),
        ('tags',            parse_tags,            re_tag_cols,        0),
        ('category',        parse_category,        re_category,        0),
        ('subject',         parse_subject,         re_subject,         0),
    ]

    endings = []
    for name, func, re_section, required in sections:
        m = re_section.search(html, prev_end)
        if not m:
            assert not required
            continue
#        assert prev_end < m.pos + m.end()
        prev_end = m.end()
        endings.append((prev_end, name))
        func(m, edition)
#    if endings != sorted(endings):
#        print sorted(endings)

def parse_edition(html):
    edition = {}
    prev_end = parse_head(html, edition)

    if not edition:
        return {}

    prev_end = parse_prod_image(html, edition, prev_end)
    prev_end = parse_title(html, edition, prev_end)
    parse_div_title(html, edition, prev_end)
    parse_sections(html, edition, prev_end)
    return edition
