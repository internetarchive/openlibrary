from lxml.etree import iterparse, tostring
import re

ns = '{http://www.abbyy.com/FineReader_xml/FineReader6-schema-v1.xml}'
page_tag = ns + 'page'
block_tag = ns + 'block'
region_tag = ns + 'region'
text_tag = ns + 'text'
rect_tag = ns + 'rect'
par_tag = ns + 'par'
line_tag = ns + 'line'
formatting_tag = ns + 'formatting'
charParams_tag = ns + 'charParams'

re_page_num = re.compile(r'^\[?\d+\]?$')

def abbyy_to_par(f, debug=False):
    prev = ''
    page_count = 0
    for event, element in iterparse(f):
        if element.tag == page_tag:
            page_count+= 1
            if debug:
                print 'page', page_count
            page_break = True
            for block in element:
                assert block.tag == block_tag
                if block.attrib['blockType'] in ('Picture', 'Table'):
                    continue
                assert block.attrib['blockType'] == 'Text'
                assert len(block) in (1, 2)
                region = block[0]
                assert region.tag == region_tag
                text = []
                if len(block) == 2:
                    e_text = block[1]
                    assert e_text.tag == text_tag
                if debug:
                    print 'block', block.attrib
                first_line_in_block = True
                for par in e_text:
                    assert par.tag == par_tag
                    text = ''
                    for line in par:
                        assert line.tag == line_tag
                        for formatting in line:
                            assert formatting.tag == formatting_tag
                            cur = ''.join(e.text for e in formatting)
                            if first_line_in_block:
                                first_line_in_block = False
                                if re_page_num.match(cur.strip()):
                                    if debug:
                                        print 'page number:', cur
                                    continue
                            if formatting[0].attrib['wordStart'] == 'true' and text and text[-1] != ' ':
                                text += ' '
                            if cur != ' ' and formatting[0].attrib['wordStart'] == 'false' and text and text[-1] == '-':
                                text = text[:-1] + cur
                            else:
                                text += cur
                            for charParams in formatting:
                                assert charParams.tag == charParams_tag
                    if text == '':
                        continue
                    if page_break:
                        if prev and text[0].islower():
                            if prev[-1] == '-':
                                prev = prev[:-1] + text
                            else:
                                prev += ' ' + text
                            continue
                        page_break = False
                    if prev:
                        yield prev
                    prev = text

            element.clear()
    if prev:
        yield prev

if __name__ == '__main__':
    import sys
    for i in abbyy_to_par(sys.stdin, debug=False):
        print i.encode('utf-8')
