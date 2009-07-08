import re
from urllib2 import urlopen
from os.path import exists

# crawl catalogue.nla.gov.au

re_th = re.compile('^<th nowrap align="RIGHT" valign="TOP">(\d{3})</th>$', re.I)
re_td = re.compile('^<td(?: VALIGN="TOP")?>(.*)</td>$')
re_span = re.compile('<span class="subfield"><strong>\|(.|&(?:gt|lt|amp);)</strong>(.*?)</span>')

trans = dict(lt='<', gt='>', amp='&')

def read_row(tag, row):
    assert len(row) == 3
    if tag[0:2] == '00':
        assert all(i == '' for i in row[0:1])
        return (tag, row[2])
    else:
        end = 0
        subfields = []
        while end != len(row[2]):
            m = re_span.match(row[2], end)
            end = m.end()
            (k, v) = m.groups()
            if len(k) != 1:
                k = trans[k[1:-1]]
            subfields.append((k, v))
        assert all(len(i) == 1 for i in row[0:1])
        return (tag, row[0], row[1], subfields)

def extract_marc(f):
    expect = 'table'
    col = 0
    row = []
    lines = []
    for line in f: # state machine
        if expect == 'table':
            if '<table border="0" class="librarianview">' in line:
                expect = 'tr'
            continue
        if expect == 'tr':
            if line.startswith('</table>'):
                break
            assert line.startswith('<tr>')
            expect = 'th'
            continue
        if expect == 'th':
            m = re_th.match(line)
            assert m
            tag = m.group(1)
            expect = 'td'
            continue
        if expect == 'td':
            if line.startswith('</tr>'):
                lines.append(read_row(tag, row))
                tag = None
                row = []
                expect = 'tr'
                continue
            if line == '<td>\n':
                expect = 'span'
                continue
            m = re_td.match(line)
            row.append(m.group(1))
            continue
        if expect == 'span':
            row.append(line[:-1])
            expect = '/td'
            continue
        if expect == '/td':
            assert line == '</td>\n'
            expect = 'td'
            continue
    return lines

i = 1
while 1:
    i+=1
    filename = 'marc/%d' % i
    if exists(filename):
        continue
    print i, 
    url = 'http://catalogue.nla.gov.au/Record/%d/Details' % i
    web_input = None
    for attempt in range(5):
        try:
            web_input = urlopen(url)
            break
        except:
            pass
    if not web_input:
        break

    out = open('marc/%d' % i, 'w')
    try:
        marc = extract_marc(web_input)
    except:
        print url
        raise
    print len(marc)
    for line in marc:
        print >> out, line
    out.close()
    #sleep(0.5)
