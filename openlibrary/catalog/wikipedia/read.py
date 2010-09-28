import sys, codecs, re
from catalog.marc.fast_parse import translate
sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

prev = None
cur_marc = []

trans = {'&':'&amp;','<':'&lt;','>':'&gt;','\n':'<br>'}
re_html_replace = re.compile('([&<>\n])')

def esc(s):
    return re_html_replace.sub(lambda m: trans[m.group(1)], s)

def esc_sp(s):
    return esc(s).replace(' ', '&nbsp;')

print '<html>\n<head><title>Authors</title></head>\n<body>'

print '87 authors with 10 or more variants in MARC records<br>'

def html_subfields(marc):
    return ''.join('<b>' + k + '</b>' + esc(translate(v)) for k, v in marc)

for line in open("matches4"):
    wiki, marc = eval(line)
    if prev and prev != wiki:
        if len(cur_marc) > 9:
            print '<h2><a href="http://en.wikipedia.org/wiki/%s">%s</a></h2>' % (prev.replace(" ", "_"), prev)
            print "%d variants in MARC records<br>" % len(cur_marc)
            print "<ul>", ''.join("<li>%s</li>\n" % html_subfields(li) for li in cur_marc), "</ul>"
#            for i in cur_marc:
#                print '  ', i
        cur_marc = []
    cur_marc.append(marc)
    prev = wiki

print '</body>\n</html>'
