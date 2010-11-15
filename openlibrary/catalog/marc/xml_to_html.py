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
        s = esc_sp(field)
    else:
        s = esc_sp(field.ind1() + field.ind2()) + ' ' + html_subfields(field)
    return u'<large>' + tag + u'</large> <code>' + s + u'</code>'

class html_record():
    def __init__(self, data):
        root = etree.fromstring(data)
        if root.tag == '{http://www.loc.gov/MARC21/slim}collection':
            root = root[0]
        rec = MarcXml(root)
        self.rec = rec
        self.leader = rec.leader()

    def html(self):
        rec = self.rec
        lines = (html_line(t, rec.decode_field(f)) for t, f in rec.all_fields())
        return '<br>\n'.join(lines)

if __name__ == '__main__':
    samples = '''1893manualofharm00jadauoft 39002054008678.yale.edu flatlandromanceo00abbouoft nybc200247 onquietcomedyint00brid secretcodeofsucc00stjo warofrebellionco1473unit zweibchersatir01horauoft cu31924091184469'''.split()

    for filename in samples:
        print 'test_data/xml_input/' + filename + '_marc.xml'
        data = open('test_data/xml_input/' + filename + '_marc.xml').read()
        if data == '':
            continue
        rec = html_record(data)
        print rec.leader
        print rec.html()
        print
