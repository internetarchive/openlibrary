from lxml import etree
from unicodedata import normalize

from openlibrary.catalog.marc.marc_base import MarcBase, MarcException

data_tag = '{http://www.loc.gov/MARC21/slim}datafield'
control_tag = '{http://www.loc.gov/MARC21/slim}controlfield'
subfield_tag = '{http://www.loc.gov/MARC21/slim}subfield'
leader_tag = '{http://www.loc.gov/MARC21/slim}leader'
record_tag = '{http://www.loc.gov/MARC21/slim}record'
collection_tag = '{http://www.loc.gov/MARC21/slim}collection'


class BlankTag(MarcException):
    pass


class BadSubtag(MarcException):
    pass


def read_marc_file(f):
    for event, elem in etree.iterparse(f, tag=record_tag):
        yield MarcXml(elem)
        elem.clear()


def norm(s):
    return normalize('NFC', str(s.replace('\xa0', ' ')))


def get_text(e):
    return norm(e.text) if e.text else ''


class DataField:
    def __init__(self, element):
        assert element.tag == data_tag
        self.element = element

    def remove_brackets(self):
        f = self.element[0]
        l = self.element[-1]
        if f.text and l.text and f.text.startswith('[') and l.text.endswith(']'):
            f.text = f.text[1:]
            l.text = l.text[:-1]

    def ind1(self):
        return self.element.attrib['ind1']

    def ind2(self):
        return self.element.attrib['ind2']

    def read_subfields(self):
        for i in self.element:
            assert i.tag == subfield_tag
            k = i.attrib['code']
            if k == '':
                raise BadSubtag
            yield k, i

    def get_lower_subfields(self):
        for k, v in self.read_subfields():
            if k.islower():
                yield get_text(v)

    def get_all_subfields(self):
        for k, v in self.read_subfields():
            yield k, get_text(v)

    def get_subfields(self, want):
        want = set(want)
        for k, v in self.read_subfields():
            if k not in want:
                continue
            yield k, get_text(v)

    def get_subfield_values(self, want):
        return [v for k, v in self.get_subfields(want)]

    def get_contents(self, want):
        contents = {}
        for k, v in self.get_subfields(want):
            if v:
                contents.setdefault(k, []).append(v)
        return contents


class MarcXml(MarcBase):
    def __init__(self, record):
        if record.tag == collection_tag:
            record = record[0]

        assert record.tag == record_tag
        self.record = record

    def leader(self):
        leader_element = self.record[0]
        if not isinstance(leader_element.tag, str):
            leader_element = self.record[1]
        assert leader_element.tag == leader_tag
        return get_text(leader_element)

    def all_fields(self):
        for i in self.record:
            if i.tag != data_tag and i.tag != control_tag:
                continue
            if i.attrib['tag'] == '':
                raise BlankTag
            yield i.attrib['tag'], i

    def read_fields(self, want):
        want = set(want)

        # http://www.archive.org/download/abridgedacademy00levegoog/abridgedacademy00levegoog_marc.xml

        non_digit = False
        for i in self.record:
            if i.tag != data_tag and i.tag != control_tag:
                continue
            tag = i.attrib['tag']
            if tag == '':
                raise BlankTag
            if tag == 'FMT':
                continue
            if not tag.isdigit():
                non_digit = True
            else:
                if tag[0] != '9' and non_digit:
                    raise BadSubtag

            if i.attrib['tag'] not in want:
                continue
            yield i.attrib['tag'], i

    def decode_field(self, field):
        if field.tag == control_tag:
            return get_text(field)
        if field.tag == data_tag:
            return DataField(field)
