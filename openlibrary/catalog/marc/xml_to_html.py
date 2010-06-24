from marc_xml import MarcXml
from lxml import etree
import re

trans = {'&':'&amp;','<':'&lt;','>':'&gt;','\n':'<br>'}
re_html_replace = re.compile('([&<>\n])')

def esc(s):
    return re_html_replace.sub(lambda m: trans[m.group(1)], s)

def esc_sp(s):
    return esc(s).replace(' ', '&nbsp;')

def html_subfields(line):
    return ''.join("<b>$%s</b>%s" % (k, esc(v)) for k, v in line.get_all_subfields())

def html_line(tag, field):
    if tag.startswith('00'):
        s = esc(field)
    else:
        s = esc_sp(field.ind1() + field.ind2()) + ' ' + html_subfields(field)
    return u'<large>' + tag + u'</large> <code>' + s + u'</code>'

def to_html(data):
    rec = MarcXml(etree.fromstring(data))
    lines = (html_line(tag, rec.decode_field(field)) for tag, field in rec.all_fields())
    return '<br>\n'.join(lines)
        
if __name__ == '__main__':
    samples = '''1893manualofharm00jadauoft 39002054008678.yale.edu flatlandromanceo00abbouoft nybc200247 onquietcomedyint00brid secretcodeofsucc00stjo warofrebellionco1473unit zweibchersatir01horauoft'''.split()

    for filename in samples:
        print 'test_data/' + filename + '_marc.xml'
        data = open('test_data/' + filename + '_marc.xml').read()
        if data == '':
            continue
        print html(data)
        print
