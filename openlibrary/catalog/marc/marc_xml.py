from lxml import etree
from unicodedata import normalize
from typing import Iterator

from openlibrary.catalog.marc.marc_base import MarcBase, MarcFieldBase, MarcException

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


def norm(s: str) -> str:
    return normalize('NFC', str(s.replace('\xa0', ' ')))


def get_text(e: etree._Element) -> str:
    return norm(e.text) if e.text else ''


class DataField(MarcFieldBase):
    def __init__(self, rec, element: etree._Element) -> None:
        assert element.tag == data_tag, f'Got {element.tag}'
        self.element = element
        assert isinstance(element, etree._Element)
        self.rec = rec
        self.tag = element.tag

    def remove_brackets(self) -> None:
        first = self.element[0]
        last = self.element[-1]
        if (
            first.text
            and last.text
            and first.text.startswith('[')
            and last.text.endswith(']')
        ):
            first.text = first.text[1:]
            last.text = last.text[:-1]

    def ind1(self):
        return self.element.attrib['ind1']

    def ind2(self):
        return self.element.attrib['ind2']

    def read_subfields(self) -> Iterator[tuple[str, etree._Element]]:
        for sub in self.element:
            assert sub.tag == subfield_tag
            k = sub.attrib['code']
            if k == '':
                raise BadSubtag
            yield k, sub

    def get_lower_subfield_values(self):
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

    def get_subfield_values(self, want: list[str]) -> list[str]:
        return [v for k, v in self.get_subfields(want)]

    def get_contents(self, want):
        contents = {}
        for k, v in self.get_subfields(want):
            if v:
                contents.setdefault(k, []).append(v)
        return contents


class MarcXml(MarcBase):
    def __init__(self, record: etree._Element) -> None:
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

    def all_fields(self) -> Iterator[tuple[str, etree._Element]]:
        for i in self.record:
            if i.tag != data_tag and i.tag != control_tag:
                continue
            if i.attrib['tag'] == '':
                raise BlankTag
            yield i.attrib['tag'], i

    def read_fields(self, want: list[str]) -> Iterator[tuple[str, str | DataField]]:
        want = set(want)

        # http://www.archive.org/download/abridgedacademy00levegoog/abridgedacademy00levegoog_marc.xml

        non_digit = False
        for f in self.record:
            if f.tag != data_tag and f.tag != control_tag:
                continue
            tag = f.attrib['tag']
            if tag == '':
                raise BlankTag
            if tag == 'FMT':
                continue
            if not tag.isdigit():
                non_digit = True
            else:
                if tag[0] != '9' and non_digit:
                    raise BadSubtag
            if f.attrib['tag'] not in want:
                continue
            yield f.attrib['tag'], self.decode_field(f)

    def decode_field(self, field) -> str | DataField:
        if field.tag == control_tag:
            return get_text(field)
        if field.tag == data_tag:
            return DataField(self, field)
