import re, os.path, urllib2
from BeautifulSoup import BeautifulSoup

# http://amazon.com/other-editions/dp/0312153325 has:
# http://www.amazon.com/gp/product/0312247869
re_link = re.compile('^http://www\.amazon\.com/(?:(.*)/dp|gp/product)/(\d{9}[\dX]|B[A-Z0-9]+)$')

desc_skip = set(['(Bargain Price)', '(Kindle Book)'])

def read_bucket_table(f):
    html = ''
    bucket = False
    table = False
    for line in f:
        if line[:-1] == '<div class="bucket">':
            bucket = True
            continue
        if bucket and line[:-1] == '   <table border="0" cellpadding="2" cellspacing="0">':
            table = True
        if table:
            html += line
            if line[:-1] == '   </table>':
                break
    return html

def parse_html(html):
    soup = BeautifulSoup(html)
    for tr in soup('tr')[2:]:
        td = tr('td')
        assert len(td) == 3
        td0 = td[0]
        assert td0['class'] == 'small'
        assert len(td0) == 3
        (nl, link, desc) = td0
        assert nl == '\n'
        href = link['href']
        if href.startswith("http://www.amazon.com:80/gp/redirect.html"):
            # audio book, skip for now
            continue
        m = re_link.match(link['href'])
        yield str(m.group(2)), desc.strip()

def get_from_amazon(isbn):
    url = 'http://www.amazon.com/dp/other-editions/' + isbn
    try:
        return urllib2.urlopen(url).read()
    except urllib2.HTTPError, error:
        if error.code != 404:
            raise
        return ''

def find_others(isbn, dir):
    filename = dir + "/" + isbn
    if len(isbn) != 10:
        return []
    if not os.path.exists(filename):
        open(filename, 'w').write(get_from_amazon(isbn))
    html = read_bucket_table(open(dir + "/" + isbn))
    if not html:
        return []
    l = [i for i in parse_html(html) if not i[0].startswith('B') and i[1] not in desc_skip]
    return l
