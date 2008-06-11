import xml.etree.ElementTree as et
import xml.parsers.expat
from parse import read_edition

data_tag = '{http://www.loc.gov/MARC21/slim}datafield'
control_tag = '{http://www.loc.gov/MARC21/slim}controlfield'
subfield_tag = '{http://www.loc.gov/MARC21/slim}subfield'

class BadSubtag:
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
            text = i.text if i.text else ''
            if i.attrib['code'] == '':
                raise BadSubtag
            self.contents.setdefault(i.attrib['code'], []).append(text)
            self.subfield_sequence.append((i.attrib['code'], text))

class xml_rec:
    def __init__(self, f):
        self.tree = et.parse(f)
        self.dataFields = {}
        self.has_blank_tag = False
        for i in self.tree.getroot():
            if i.tag == data_tag or i.tag == control_tag:
                if i.attrib['tag'] == '':
                    self.has_blank_tag = True
                else:
                    self.dataFields.setdefault(i.attrib['tag'], []).append(i)

    def fields(self):
        return self.dataFields.keys()

    def get_field(self, tag, default=None):
        if tag not in self.dataFields:
            return default
        assert len(self.dataFields[tag]) == 1
        element = self.dataFields[tag][0]
        if element.tag == control_tag:
            return element.text if element.text else ''
        if element.tag == data_tag:
            return datafield(element)
        return default

    def get_fields(self, tag):
        if tag not in self.dataFields:
            return []
        if self.dataFields[tag][0].tag == control_tag:
            return [i.text if i.text else '' for i in self.dataFields[tag]]
        if self.dataFields[tag][0].tag == data_tag:
            return [datafield(i) for i in self.dataFields[tag]]
        return []

def parse(f):
    rec = xml_rec(f)
    edition = {}
    if rec.has_blank_tag or not read_edition(rec, edition):
        return {}
    return edition
