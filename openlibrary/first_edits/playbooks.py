"""One playbook per field: the question in plain words, the conventions a
newcomer needs, and where to double-check outside Open Library.

Copy lives here rather than in templates so the wizard template stays one
shape for every field. Strings are resolved per request for i18n.
"""

from dataclasses import dataclass
from dataclasses import field as dc_field

from openlibrary.i18n import gettext as _

HELP_BASE = "https://openlibrary.org/help/faq/editing"


@dataclass(frozen=True)
class Note:
    text: str
    href: str | None = None


@dataclass(frozen=True)
class LinkOut:
    label: str
    url: str


@dataclass(frozen=True)
class Playbook:
    field: str
    label: str
    questions: dict[str, str]
    why: str
    notes: list[Note] = dc_field(default_factory=list)
    keep_label: str = ""
    other_label: str = ""
    other_placeholder: str = ""
    input_type: str = "text"

    def question(self, mode: str) -> str:
        return self.questions.get(mode) or self.questions["fill"]


def get_playbooks() -> dict[str, Playbook]:
    return {
        "languages": Playbook(
            field="languages",
            label=_("Language"),
            questions={
                "fill": _("What language is this edition written in?"),
                "check": _("Is the language on this edition right?"),
            },
            why=_("Language decides which readers find this edition in search and which editions get grouped together."),
            notes=[
                Note(
                    _("Record the language of the text, not the language of the title page. A translation is in the language it was translated into."),
                    f"{HELP_BASE}#edit-metadata-language",
                ),
            ],
            keep_label=_("Keep what Open Library has"),
            other_label=_("A different language"),
            other_placeholder=_("Start typing a language"),
        ),
        "number_of_pages": Playbook(
            field="number_of_pages",
            label=_("Page count"),
            questions={
                "fill": _("How many pages does this edition have?"),
                "check": _("Is the page count on this edition right?"),
            },
            why=_("Page count helps readers tell editions apart and helps librarians spot duplicates."),
            notes=[
                Note(
                    _(
                        "Catalogs count front matter differently, so numbers within a few pages of each other are the same count. "
                        "Use the last numbered page of the main text."
                    ),
                    f"{HELP_BASE}#pages",
                ),
            ],
            keep_label=_("Keep what Open Library has"),
            other_label=_("A different number"),
            other_placeholder=_("Number of pages"),
            input_type="number",
        ),
        "publishers": Playbook(
            field="publishers",
            label=_("Publisher"),
            questions={
                "fill": _("Who published this edition?"),
                "check": _("Is the publisher on this edition right?"),
            },
            why=_("The publisher is how readers and booksellers tell one edition from another, and it is where many imported records go wrong."),
            notes=[
                Note(
                    _("Open Library records the imprint printed on the book, not the parent company. Anchor Books, not Penguin Random House."),
                    f"{HELP_BASE}#publisher",
                ),
                Note(_("Match the spelling other editions of this work already use, so the publisher page stays in one piece."), f"{HELP_BASE}#publisher"),
            ],
            keep_label=_("Keep what Open Library has"),
            other_label=_("A different publisher"),
            other_placeholder=_("Start typing a publisher"),
        ),
        "subtitle": Playbook(
            field="subtitle",
            label=_("Subtitle"),
            questions={
                "fill": _("Does this edition have a subtitle?"),
                "check": _("Is the subtitle on this edition right?"),
            },
            why=_("Subtitles are often on the cover but missing from imported records."),
            notes=[
                Note(
                    _("A tagline like “A Novel” or a series name is not a subtitle. Subtitles appear on the title page after a colon or line break."),
                    f"{HELP_BASE}#subtitle",
                ),
            ],
            keep_label=_("Keep what Open Library has"),
            other_label=_("A different subtitle"),
            other_placeholder=_("Subtitle as printed"),
        ),
        "publish_date": Playbook(
            field="publish_date",
            label=_("Publish date"),
            questions={
                "fill": _("When was this edition published?"),
                "check": _("Is the publish date on this edition right?"),
            },
            why=_("The date tells editions apart and orders them on the work page."),
            notes=[
                Note(
                    _("Publishers reuse one ISBN across printings, so catalogs can disagree by years. Record the date of the first printing under this ISBN."),
                    f"{HELP_BASE}#date",
                ),
            ],
            keep_label=_("Keep what Open Library has"),
            other_label=_("A different date"),
            other_placeholder=_("Year, or a full date"),
        ),
    }


def link_outs(isbn13: str | None, title: str | None = None) -> list[LinkOut]:
    """Where to double-check outside Open Library, opened on this ISBN. Link only, never imported."""
    if not isbn13:
        return []
    return [
        LinkOut(_("WorldCat"), f"https://search.worldcat.org/search?q=bn:{isbn13}"),
        LinkOut(_("Google Books"), f"https://books.google.com/books?vid=ISBN{isbn13}"),
        LinkOut(_("Amazon"), f"https://www.amazon.com/s?k={isbn13}"),
        LinkOut(_("Goodreads"), f"https://www.goodreads.com/search?q={isbn13}"),
    ]
