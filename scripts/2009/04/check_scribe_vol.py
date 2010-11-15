import web, re, urllib2, sys
from catalog.read_rc import read_rc
from catalog.get_ia import find_item
import xml.etree.ElementTree as et

re_ia_vol = re.compile('[^0-9](\d{2,3})[^0-9]+$')
re_txt_vol = re.compile(r'\bVOL(?:UME)?\b', re.I)

rc = read_rc()

def get_vol_from_xml(base, ia):
    meta = base + '/' + ia + '_meta.xml'
    try:
        tree = et.parse(urllib2.urlopen(meta))
    except urllib2.HTTPError:
        return None
    except urllib2.URLError:
        return None
    for e in tree.getroot():
        if e.tag =='volume':
            return e.text
    return None

def check_text(base, ia, vol):
    url = base + '/' + ia + '_djvu.txt'
    ureq = urllib2.Request(url, None, {'Range':'bytes=0-5000'})
    return urllib2.urlopen(ureq).read()
    for line in urllib2.urlopen(ureq):
        if re_txt_vol.search(line):
            return line[:-1]

def vol_ia():
    assert False
    ia_db = web.database(dbn='mysql', db='archive', user=rc['ia_db_user'], pw=rc['ia_db_pass'], host=rc['ia_db_host'])
    ia_db.printing = False
    iter = ia_db.query("select identifier from metadata where scanner is not null and scanner != 'google' and noindex is null and mediatype='texts' and curatestate='approved'")
    out = open('vol_ia', 'w')
    print 'start iter'
    for row in iter:
        ia = row.identifier
        m = re_ia_vol.search(ia)
        if not m or m.group(1) == '00':
            continue
        print >> out, ia
    out.close()
    sys.exit(0)

out = open('vol_check3', 'w')
skip = True
for line in open('vol_ia'):
    ia = line[:-1]
    if skip:
        if ia == 'bengalin175657se02hilluoft':
            skip = False
        continue
    m = re_ia_vol.search(ia)
    if not m or m.group(1) == '00':
        continue
    (host, path) = find_item(ia)
    print ia
    if not host or not path:
        continue
    base = "http://" + host + path
    vol = get_vol_from_xml(base, ia)
    if not vol or not vol.isdigit():
        continue
    try:
#        vol_line = check_text(base, ia, vol)
        txt = check_text(base, ia, vol)
    except urllib2.HTTPError:
        continue
    except urllib2.URLError:
        continue
    #print >> out, (vol, ia, vol_line)
    print >> out, `(vol, ia, txt)`
out.close()
