import os, re, sys, codecs, dbhash
from catalog.amazon.other_editions import read_bucket_table, parse_html
from catalog.infostore import get_site

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)
db = dbhash.open("/2/pharos/isbn/isbn_to_marc.dbm", 'r')

site = get_site()

desc_skip = set(['(Bargain Price)', '(Kindle Book)'])

dir = sys.argv[1]
for filename in os.listdir(dir):
    if not filename[0].isdigit():
        continue
    html = read_bucket_table(open(dir + "/" + filename))
    if not html:
        continue
    l = [i for i in parse_html(html, filename) if not i[0].startswith('B') and i[1] not in desc_skip]
    if not l:
        continue
    for k in site.things({'isbn_10': filename, 'type': '/type/edition'}):
        t = site.withKey(k)
        num = len(t.isbn_10)
        if num == 1:
            num = ''
        print filename, k, t.title, num
    for asin, extra in l:
        things = site.things({'isbn_10': asin, 'type': '/type/edition'})
        if things:
            for k in things:
                t = site.withKey(k)
                num = len(t.isbn_10)
                if num == 1:
                    num = ''
                print asin, k, t.title, extra, num
        else:
            print asin, extra

    print
