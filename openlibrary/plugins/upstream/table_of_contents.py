import json
from dataclasses import dataclass
from functools import cached_property
from typing import Required, TypedDict, TypeVar

import web

from infogami.infobase.client import Nothing, Thing
from openlibrary.core.models import ThingReferenceDict


@dataclass
class TableOfContents:
    entries: list['TocEntry']

    @cached_property
    def min_level(self) -> int:
        return min(e.level for e in self.entries)

    def is_complex(self) -> bool:
        return any(e.extra_fields for e in self.entries)

    @staticmethod
    def from_db(
        db_table_of_contents: list[dict] | list[str] | list[str | dict],
    ) -> 'TableOfContents':
        def row(r: dict | str) -> 'TocEntry':
            if isinstance(r, str):
                # Legacy, can be just a plain string
                return TocEntry(level=0, title=r)
            else:
                return TocEntry.from_dict(r)

        return TableOfContents(
            [
                toc_entry
                for r in db_table_of_contents
                if not (toc_entry := row(r)).is_empty()
            ]
        )

    def to_db(self) -> list[dict]:
        return [r.to_dict() for r in self.entries]

    @staticmethod
    def from_markdown(text: str) -> 'TableOfContents':
        return TableOfContents(
            [
                TocEntry.from_markdown(line)
                for line in text.splitlines()
                if line.strip(" |")
            ]
        )

    def to_markdown(self) -> str:
        return "\n".join(
            ('    ' * (r.level - self.min_level)) + r.to_markdown()
            for r in self.entries
        )


class AuthorRecord(TypedDict, total=False):
    name: Required[str]
    author: ThingReferenceDict | None


@dataclass
class TocEntry:
    level: int
    label: str | None = None
    title: str | None = None
    pagenum: str | None = None

    authors: list[AuthorRecord] | None = None
    subtitle: str | None = None
    description: str | None = None

    @cached_property
    def extra_fields(self) -> dict:
        required_fields = ('level', 'label', 'title', 'pagenum')
        extra_fields = self.__annotations__.keys() - required_fields
        return {
            field: getattr(self, field)
            for field in extra_fields
            if getattr(self, field) is not None
        }

    @staticmethod
    def from_dict(d: dict) -> 'TocEntry':
        return TocEntry(
            level=d.get('level', 0),
            label=d.get('label'),
            title=d.get('title'),
            pagenum=d.get('pagenum'),
            authors=d.get('authors'),
            subtitle=d.get('subtitle'),
            description=d.get('description'),
        )

    def to_dict(self) -> dict:
        return {key: value for key, value in self.__dict__.items() if value is not None}

    @staticmethod
    def from_markdown(line: str) -> 'TocEntry':
        """
        Parse one row of table of contents.

        >>> def f(text):
        ...     d = TocEntry.from_markdown(text)
        ...     return (d.level, d.label, d.title, d.pagenum)
        ...
        >>> f("* chapter 1 | Welcome to the real world! | 2")
        (1, 'chapter 1', 'Welcome to the real world!', '2')
        >>> f("Welcome to the real world!")
        (0, None, 'Welcome to the real world!', None)
        >>> f("** | Welcome to the real world! | 2")
        (2, None, 'Welcome to the real world!', '2')
        >>> f("|Preface | 1")
        (0, None, 'Preface', '1')
        >>> f("1.1 | Apple")
        (0, '1.1', 'Apple', None)
        """
        RE_LEVEL = web.re_compile(r"(\**)(.*)")
        level, text = RE_LEVEL.match(line.strip()).groups()

        if "|" in text:
            tokens = text.split("|", 3)
            label, title, page, extra_fields = pad(tokens, 4, '')
        else:
            title = text
            label = page = ""
            extra_fields = ''

        return TocEntry(
            level=len(level),
            label=label.strip() or None,
            title=title.strip() or None,
            pagenum=page.strip() or None,
            **json.loads(extra_fields or '{}'),
        )

    def to_markdown(self) -> str:
        result = ' | '.join(
            (
                '*' * self.level
                + (' ' if self.label and self.level else '')
                + (self.label or ''),
                self.title or '',
                self.pagenum or '',
            )
        )

        if self.extra_fields:
            # We might have `Thing` objects instead of plain dicts...
            result += ' | ' + json.dumps(self.extra_fields, cls=InfogamiThingEncoder)

        return result

    def is_empty(self) -> bool:
        return all(
            getattr(self, field) is None
            for field in self.__annotations__
            if field != 'level'
        )


T = TypeVar('T')


def pad(seq: list[T], size: int, e: T) -> list[T]:
    """
    >>> pad([1, 2], 4, 0)
    [1, 2, 0, 0]
    """
    seq = seq[:]
    while len(seq) < size:
        seq.append(e)
    return seq


class InfogamiThingEncoder(json.JSONEncoder):
    def default(self, obj):
        """
        Custom JSON encoder for Infogami Thing objects.
        """
        if isinstance(obj, Thing):
            return obj.dict()
        if isinstance(obj, Nothing):
            return None
        return super().default(obj)
