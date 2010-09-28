from xml.etree.cElementTree import iterparse, tostring, Element
import sys, re

ns = '{http://www.abbyy.com/FineReader_xml/FineReader6-schema-v1.xml}'
page_tag = ns + 'page'

re_par_end_dot = re.compile(r'\.\W*$')

class PageBreak (object):
    def __init__(self, page_num):
        self.page_num = page_num

def read_text_line(line):
    text = ''
    for fmt in line:
        for c in fmt:
            text += c.text
    return text

def par_text(lines):
    cur = ''
    for line_num, line in enumerate(lines):
        first_char = line[0][0]
        if first_char.attrib['wordStart'] == 'false' or first_char.attrib['wordFromDictionary'] == 'false' and cur.endswith('- '):
            cur = cur[:-2]
        for fmt in line:
            cur += ''.join(c.text for c in fmt)
        if line_num + 1 != len(lines):
            cur += ' '
    return cur

def line_end_dot(line):
    return bool(re_par_end_dot.search(read_text_line(line)))

def par_unfinished(last_line, page_w):
    last_line_len = sum(len(fmt) for fmt in last_line)
    if last_line_len < 15 or line_end_dot(last_line):
        return False
    last_line_last_char = last_line[-1][-1]
    r = float(last_line_last_char.attrib['r'])
    return r / page_w > 0.75

def col_unfinished(last_line):
    return sum(len(fmt) for fmt in last_line) > 14 and not line_end_dot(last_line)

def par_iter(ia):
    f = open(ia + '_abbyy')
    incomplete_par = None
    end_column_par = None
    skipped_par = []
    #for page_num, (eve, page) in enumerate(iterparse(f, tag=page_tag)):
    for page_num, (eve, page) in enumerate(iterparse(f)):
        if page.tag != page_tag:
            continue
        if incomplete_par is None:
            yield [PageBreak(page_num)]

        page_w = float(page.attrib['width'])
        assert page.tag == page_tag

        for block_num, block in enumerate(page):
            if block.attrib['blockType'] != 'Text':
                continue
            region, text = block
            for par_num, par in enumerate(text):
                if len(par) == 0 or len(par[0]) == 0 or len(par[0][0]) == 0:
                    continue
                last_line = par[-1]
                if end_column_par is not None:
                    if line_end_dot(last_line) and int(par[0].attrib['t']) < int(end_column_par[0].attrib['b']):
                        print 'end column par'
                        yield list(end_column_par) + list(par)
                        end_column_par = None
                        continue
                    else:
                        yield list(end_column_par)
                    end_column_par = None

                if incomplete_par is not None:
                    if line_end_dot(last_line):
                        yield list(incomplete_par) + [PageBreak(page_num)] + list(par)
                        for p in skipped_par:
                            yield list(p)
                        incomplete_par = None
                        skipped_par = []
                    else:
                        skipped_par.append(par)
                elif par_num + 1 == len(text) and block_num + 1 == len(page) and par_unfinished(last_line, page_w):
                        incomplete_par = par
                elif par_num + 1 == len(text) and block_num + 1 != len(page) and col_unfinished(last_line):
                        end_column_par = par
                else:
                    yield list(par)

        page.clear()

for lines in par_iter(sys.argv[1]):
    lines = [l for l in lines if not isinstance(l, PageBreak)]
    text = par_text(lines)
    print text.encode('utf-8')
    print
