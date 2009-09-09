from catalog.utils import pick_first_date
import web, re, sys, codecs
sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

re_marc_name = re.compile('^(.*), (.*)$')
re_end_dot = re.compile('[^ ][^ ]\.$', re.UNICODE)

def flip_name(name):
    # strip end dots like this: "Smith, John." but not like this: "Smith, J."
    m = re_end_dot.search(name)
    if m:
        name = name[:-1]

    m = re_marc_name.match(name)
    return m.group(2) + ' ' + m.group(1)

for wikipedia, marc in (eval(i) for i in open("matches4")):
    dates = pick_first_date(v for k, v in marc if k == 'd')
    name = ' '.join(v for k, v in marc if k in 'abc')
    print name
    if ', ' in name:
        print flip_name(name)
    print dates

