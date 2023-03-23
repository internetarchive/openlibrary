import re
from abc import abstractmethod
from collections import defaultdict
from collections.abc import Iterator

re_isbn = re.compile(r'([^ ()]+[\dX])(?: \((?:v\. (\d+)(?: : )?)?(.*)\))?')
# handle ISBN like: 1402563884c$26.95
re_isbn_and_price = re.compile(r'^([-\d]+X?)c\$[\d.]+$')


class MarcException(Exception):
    # Base MARC exception class
    pass


class BadMARC(MarcException):
    pass


class NoTitle(MarcException):
    pass


class MarcFieldBase:
    rec: "MarcBase"

    @abstractmethod
    def ind1(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def ind2(self) -> str:
        raise NotImplementedError

    def get_subfield_values(self, want: str) -> list[str]:
        return [v.strip() for _, v in self.get_subfields(want) if v]

    @abstractmethod
    def get_all_subfields(self) -> Iterator[tuple[str, str]]:
        raise NotImplementedError

    def get_contents(self, want: str) -> dict[str, list[str]]:
        contents = defaultdict(list)
        for k, v in self.get_subfields(want):
            if v:
                contents[k].append(v)
        return contents

    def get_subfields(self, want: str) -> Iterator[tuple[str, str]]:
        for k, v in self.get_all_subfields():
            if k in want:
                yield k, v

    def get_lower_subfield_values(self) -> Iterator[str]:
        for k, v in self.get_all_subfields():
            if k.islower():
                yield v


class MarcBase:
    def read_isbn(self, f: MarcFieldBase) -> list[str]:
        found = []
        for v in f.get_subfield_values('az'):
            m = re_isbn_and_price.match(v)
            if not m:
                m = re_isbn.match(v)
            if not m:
                continue
            found.append(m.group(1))
        return found

    def get_control(self, tag: str) -> str | None:
        control = self.read_fields([tag])
        _, v = next(control, (tag, None))
        assert isinstance(v, (str, type(None)))
        if tag == '008' and v:
            # Handle duplicate 008s, even though control fields are non-repeatable.
            if others := [str(d) for _, d in list(control) if len(str(d)) == 40]:
                return min(others + [v], key=lambda s: s.count(' '))
        return v

    def get_fields(self, tag: str) -> list[MarcFieldBase]:
        return [v for _, v in self.read_fields([tag]) if isinstance(v, MarcFieldBase)]

    @abstractmethod
    def read_fields(self, want: list[str]) -> Iterator[tuple[str, str | MarcFieldBase]]:
        raise NotImplementedError

    def get_linkage(self, original: str, link: str) -> MarcFieldBase | None:
        """
        :param original str: The original field e.g. '245'
        :param link str: The linkage {original}$6 value e.g. '880-01'
        :rtype: MarcFieldBase | None
        :return: alternate script field (880) corresponding to original, or None
        """
        linkages = self.read_fields(['880'])
        target = link.replace('880', original)
        for tag, f in linkages:
            assert isinstance(f, MarcFieldBase)
            if f.get_subfield_values('6')[0].startswith(target):
                return f
        return None
