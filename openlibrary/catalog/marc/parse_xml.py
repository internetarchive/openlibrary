from lxml import etree
import xml.parsers.expat
from parse import read_edition
from unicodedata import normalize

slim = '{http://www.loc.gov/MARC21/slim}'
leader_tag = slim + 'leader'
data_tag = slim + 'datafield'
control_tag = slim + 'controlfield'
subfield_tag = slim + 'subfield'
collection_tag = slim + 'collection'
record_tag = slim + 'record'

def norm(s):
    return normalize('NFC', unicode(s))

class BadSubtag:
    pass

class MultipleTitles:
    pass

class MultipleWorkTitles:
    pass

class datafield:
    def __init__(self, element):
        assert element.tag == data_tag
        self.contents = {}
        self.subfield_sequence = []
        self.indicator1 = element.attrib['ind1']
        self.indicator2 = element.attrib['ind2']
        for i in element:
            assert i.tag == subfield_tag
            text = norm(i.text) if i.text else u''
            if i.attrib['code'] == '':
                raise BadSubtag
            self.contents.setdefault(i.attrib['code'], []).append(text)
            self.subfield_sequence.append((i.attrib['code'], text))

class xml_rec:
    def __init__(self, f):
        self.root = etree.parse(f).getroot()
        if self.root.tag == collection_tag:
            assert self.root[0].tag == record_tag
            self.root = self.root[0]
        self.dataFields = {}
        self.has_blank_tag = False
        for i in self.root:
            if i.tag == data_tag or i.tag == control_tag:
                if i.attrib['tag'] == '':
                    self.has_blank_tag = True
                else:
                    self.dataFields.setdefault(i.attrib['tag'], []).append(i)

    def leader(self):
        leader = self.root[0]
        assert leader.tag == leader_tag
        return norm(leader.text)

    def fields(self):
        return self.dataFields.keys()

    def get_field(self, tag, default=None):
        if tag not in self.dataFields:
            return default
        if tag == '245' and len(self.dataFields[tag]) > 1:
            raise MultipleTitles
        if tag == '240' and len(self.dataFields[tag]) > 1:
            raise MultipleWorkTitles
        if tag != '006':
            assert len(self.dataFields[tag]) == 1
        element = self.dataFields[tag][0]
        if element.tag == control_tag:
            return norm(element.text) if element.text else u''
        if element.tag == data_tag:
            return datafield(element)
        return default

    def get_fields(self, tag):
        if tag not in self.dataFields:
            return []
        if self.dataFields[tag][0].tag == control_tag:
            return [norm(i.text) if i.text else u'' for i in self.dataFields[tag]]
        if self.dataFields[tag][0].tag == data_tag:
            return [datafield(i) for i in self.dataFields[tag]]
        return []

def parse(f):
    rec = xml_rec(f)
    edition = {}
    if rec.has_blank_tag:
        print 'has blank tag'
    if rec.has_blank_tag or not read_edition(rec, edition):
        return {}
    return edition
