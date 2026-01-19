"""The sort menu shown above search results, reading log shelves, lists, author works and languages.

``SortMenu.build`` turns plain values (the page's path and query, the selected sort, who is
looking) into everything ``search/sort_options.html.jinja`` renders, so the template reads
nothing from the request. FastAPI routes build it from their request; web.py templates call
``sort_menu`` (in ``openlibrary/plugins/worksearch/code.py``), which reads web.py's.
"""

import json
import urllib.parse
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Self

from openlibrary.i18n import gettext as _

type SortScheme = Literal["works", "authors", "lists_seeds", "languages", "reading_log"]


@dataclass(frozen=True)
class SortOption:
    sort: str
    name: str
    ga_key: str
    sub_sorts: tuple[SortOption, ...] = ()


@dataclass(frozen=True)
class SortMenuItem:
    value: str
    label: str
    url: str
    track: str
    nested: bool = False

    def as_json(self) -> dict:
        """What sort_options.js reads; ``nested`` only when set."""
        item = {"value": self.value, "label": self.label, "url": self.url, "track": self.track}
        return (item | {"nested": True}) if self.nested else item


def _options(scheme: SortScheme, selected_sort: str, can_see_beta_sorts: bool) -> list[SortOption]:
    if scheme == "authors":
        options = [
            SortOption("relevance", _("Relevance"), "Relevance"),
            SortOption("name", _("Name"), "Name"),
            SortOption("work_count desc", _("Work Count"), "WorkCountDesc"),
            SortOption("random", _("Random"), "Random"),
        ]
        if selected_sort in ("birth_timestamp asc", "birth_timestamp desc") or can_see_beta_sorts:
            options += [
                SortOption("birth_timestamp asc", _("Birth Date (oldest) (beta: Librarian only)"), "BirthDateOldest"),
                SortOption("birth_timestamp desc", _("Birth Date (youngest) (beta: Librarian only)"), "BirthDateYoungest"),
            ]
        return options
    if scheme == "lists_seeds":
        return [
            SortOption("index", _("List Order"), "ListOrder"),
            SortOption("added", _("Recently Added"), "RecentlyAdded"),
            SortOption("title", _("Title"), "ListTitle"),
            SortOption("last_modified", _("Recently Edited"), "LastModified"),
        ]
    if scheme == "languages":
        return [
            SortOption("count", _("Work Count"), "WorkCount"),
            SortOption("name", _("Language Name"), "LanguageName"),
            SortOption("ebook_edition_count", _("Ebook Edition Count"), "EbookEditionCount"),
        ]
    if scheme == "reading_log":
        return [
            SortOption("desc", _("Date Added (newest)"), "DateAddedNewest"),
            SortOption("asc", _("Date Added (oldest)"), "DateAddedOldest"),
            SortOption("title", _("Title"), "ShelfTitle"),
            SortOption("old", _("First Published"), "ShelfOld"),
            SortOption("rating", _("Your Top Rated"), "ShelfYourRating"),
            SortOption("want_to_read", _("Most Wanted"), "ShelfMostWanted"),
        ]
    options = [
        SortOption("relevance", _("Relevance"), "Relevance"),
        SortOption("editions", _("Most Editions"), "Editions"),
        SortOption("old", _("First Published"), "Old"),
        SortOption("new", _("Most Recent"), "New"),
        SortOption("rating", _("Top Rated"), "Rating"),
        SortOption(
            "readinglog",
            _("Reading Log"),
            "ReadingLog",
            sub_sorts=(
                SortOption("readinglog", _("Any"), "ReadingLogAny"),
                SortOption("want_to_read", _("Want to Read"), "ReadingLogWantToRead"),
                SortOption("currently_reading", _("Currently Reading"), "ReadingLogCurrentlyReading"),
                SortOption("already_read", _("Already Read"), "ReadingLogAlreadyRead"),
                SortOption("stopped_reading", _("Stopped Reading"), "ReadingLogStoppedReading"),
            ),
        ),
        SortOption("trending", _("Trending"), "Trending"),
        SortOption("random", _("Random"), "Random"),
    ]
    if selected_sort == "title" or can_see_beta_sorts:
        options.append(SortOption("title", _("Work Title (beta: Librarian only)"), "Title"))
    return options


def _find(options: Collection[SortOption], sort: str) -> SortOption | None:
    for option in options:
        if option.sort == sort:
            return option
        if sub := _find(option.sub_sorts, sort):
            return sub
    return None


def with_query(path: str, params: Mapping[str, str], **changes: str | None) -> str:
    """``path`` with ``params`` updated by ``changes`` (``None`` removes a key), as Templetor's ``changequery`` builds it."""
    query = dict(params)
    for key, value in changes.items():
        if value is None:
            query.pop(key, None)
        else:
            query[key] = value
    return path + ("?" + urllib.parse.urlencode(query) if query else "")


@dataclass(frozen=True)
class SortMenu:
    """What ``search/sort_options.html.jinja`` renders."""

    selected_value: str
    selected_label: str
    items: tuple[SortMenuItem, ...]
    shuffle_href: str | None  # the "Shuffle" link, shown while a random sort is selected (never to bots)

    @property
    def items_json(self) -> str:
        return json.dumps([item.as_json() for item in self.items])

    @classmethod
    def build(
        cls,
        selected_sort: str | None,
        *,
        path: str,
        params: Mapping[str, str],
        scheme: SortScheme = "works",
        default_sort: str = "relevance",
        exclude: Collection[str] = (),
        can_see_beta_sorts: bool = False,
        is_bot: bool = False,
        now: datetime | None = None,
    ) -> Self:
        """``params`` holds one value per key, the last if repeated, as ``web.input()`` does."""
        selected_sort = selected_sort or default_sort
        options = _options(scheme, selected_sort, can_see_beta_sorts)
        # Any random_<seed> sort shows as "Random"; it falls back to the default where there's no Random option.
        selected_key = "random" if selected_sort.startswith("random") else selected_sort
        selected = _find(options, selected_key) or _find(options, default_sort)
        assert selected, f"no {default_sort!r} sort in the {scheme!r} menu"

        def url(sort: str) -> str:
            return with_query(path, params, page=None, sort=None if sort == default_sort else sort)

        items: list[SortMenuItem] = []
        for option in options:
            if option.sort in exclude:
                continue
            items.append(SortMenuItem(option.sort, option.name, url(option.sort), option.ga_key))
            # Sub-sorts become `nested` rows, always visible. A sub-sort repeating its parent's key
            # (Reading Log / "Any") is dropped: the parent already selects it, and both rows would read as checked.
            items += [
                SortMenuItem(sub.sort, sub.name, url(sub.sort), option.ga_key + "SubSort", nested=True) for sub in option.sub_sorts if sub.sort != option.sort
            ]

        shuffle_href = (
            with_query(path, params, page=None, sort=f"random_{(now or datetime.now()).timestamp()}")
            if selected_sort.startswith("random") and not is_bot
            else None
        )
        return cls(selected.sort, selected.name, tuple(items), shuffle_href)
