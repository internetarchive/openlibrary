from mechanize import Browser
import re, os.path
from openlibrary.catalog.read_rc import read_rc

rc = read_rc()

start = "http://authorities.loc.gov/cgi-bin/Pwebrecon.cgi?DB=local&PAGE=First"
def get_table_rows(fh):
    cur = ''
    expect = 'thesauri'
    for line in fh:
        if expect == 'thesauri':
            if line == '<TH><a href="/help/thesauri.htm">Type of Heading</a></TH>\n':
                expect = 'headings_close_tr'
                continue
        if expect == 'headings_close_tr':
            assert line == '</TR>\n'
            expect = 'tr'
            continue
        if expect == 'tr':
            assert line == '<TR>\n'
            expect = 'center'
            continue
        if expect == 'center':
            if line == '<TR>\n':
                yield cur.decode('utf-8')
                cur = ''
            elif line == '</CENTER>\n':
                yield cur.decode('utf-8')
                break
            else:
                cur += line
            continue

re_row = re.compile('^<TD ALIGN=RIGHT VALIGN=TOP >\n<A HREF="/cgi-bin/Pwebrecon\.cgi\?(.*)"\n><IMG SRC="/images/([^.]+)\.gif" BORDER=0 ALT="(?:[^"]+)"></A>\n(\d+)\n</TD>\n<TD ALIGN=RIGHT>\n(\d+)\n</TD>\n<TD ALIGN=LEFT>\n(.+)\n</TD>\n<TD ALIGN=LEFT>\n(.+)\n</TD>\n$')
re_no_link = re.compile('^<TD ALIGN=RIGHT VALIGN=TOP >\n</A>\n\d+\n</TD>\n<TD ALIGN=RIGHT>')

def read_serp(fh):
    cur_row = 0
    for row in get_table_rows(fh):
        cur_row += 1
        if re_no_link.match(row):
            continue
        m = re_row.match(row)
        if not m:
            print row
        (param, a, row_num, bib_records, heading, type_of_heading) = m.groups()
        assert str(cur_row) == row_num
        yield {
            'a': a,
            'bib_records': bib_records,
            'heading': heading,
            'type': type_of_heading
        }

def search(arg):
    assert '/' not in arg # because we use it in a filename
    cache = rc['authority_cache']
    filename = cache + '/' + arg
    if os.path.exists(filename):
        return [eval(i) for i in open(filename)]
    br = Browser()
    br.set_handle_robots(False)
    br.open(start)
    br.select_form(name="querybox")
    br['Search_Arg'] = arg.encode('utf-8')
    br['Search_Code'] = ['NHED_']
    res = br.submit()
    found = list(read_serp(res))
    br.close()
    out = open(filename, 'w')
    for i in found:
        print >> out, i
    out.close()
    return found

def test_harold_osman_kelly():
    arg = 'Kelly, Harold Osman'
    found = search(arg)
    assert found[0]['heading'] == 'Kelly, Harold Osman, 1884-1955'

def test_jesus():
    arg = 'Jesus Christ'
    found = search(arg)
    assert found[0]['heading'] == 'Jesus Christ'

def test_pope_sixtus():
    arg = 'Sixtus V Pope'
    found = search(arg)
    assert found[0]['heading'] == 'Sixtus V, Pope, 1520-1590'

def test_william_the_conqueror():
    arg = 'William I King of England'
    found = search(arg)
    assert found[0]['heading'] == 'William I, King of England, 1027 or 8-1087'

def test_non_ascii_result():
    arg = 'Asoka King of Magadha'
    found = search(arg)
    assert found[0]['heading'] == u'As\u0301oka, King of Magadha, fl. 259 B.C.'

def test_non_ascii_param():
    arg = u'A\u015boka King of Magadha'
    found = search(arg)
    assert found[0]['heading'] == u'As\u0301oka, King of Magadha, fl. 259 B.C.'
