"""One playbook per field: the question in plain words, the conventions a
newcomer needs, and where to double-check outside Open Library.

Copy lives here rather than in templates so the wizard template stays one
shape for every field. Strings are resolved per request for i18n.
"""

from dataclasses import dataclass
from dataclasses import field as dc_field

from openlibrary.i18n import gettext as _

HELP_BASE = "https://openlibrary.org/help/faq/editing"
# The Library of Congress and OCLC syntax rules Open Library's normalizers implement.
LCCN_SPEC = "https://www.loc.gov/marc/lccn-namespace.html"
OCLC_SPEC = "https://help.oclc.org/Librarian_Toolbox/Searching_WorldCat_Indexes/Bibliographic_records/OCLC_control_number"


@dataclass(frozen=True)
class Note:
    text: str
    href: str | None = None


@dataclass(frozen=True)
class Trap:
    """A way this edit goes wrong. ``checked_by`` names the live check that
    catches it, so the page can be honest about which mistakes it cannot see."""

    text: str
    checked_by: str | None = None


@dataclass(frozen=True)
class LinkOut:
    label: str
    url: str


@dataclass(frozen=True)
class Playbook:
    field: str
    label: str
    questions: dict[str, str]
    actions: dict[str, str] = dc_field(default_factory=dict)
    why: str = ""
    notes: list[Note] = dc_field(default_factory=list)
    traps: list[Trap] = dc_field(default_factory=list)
    keep_label: str = ""
    other_label: str = ""
    other_placeholder: str = ""
    input_type: str = "text"

    def question(self, mode: str) -> str:
        return self.questions.get(mode) or self.questions["fill"]

    def action(self, mode: str) -> str:
        return self.actions.get(mode) or self.label


def get_playbooks() -> dict[str, Playbook]:
    return {
        "languages": Playbook(
            field="languages",
            label=_("Language"),
            actions={"fill": _("Fill in language"), "check": _("Check language")},
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
            actions={"fill": _("Fill in page count"), "check": _("Check page count")},
            questions={
                "fill": _("How many pages does this edition have?"),
                "check": _("Is the page count on this edition right?"),
            },
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
            actions={"fill": _("Fill in publisher"), "check": _("Check publisher")},
            questions={
                "fill": _("Who published this edition?"),
                "check": _("Is the publisher on this edition right?"),
            },
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
            actions={"fill": _("Fill in subtitle"), "check": _("Check subtitle")},
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
            actions={"fill": _("Fill in publish date"), "check": _("Check publish date")},
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
        "lccn": Playbook(
            field="lccn",
            label=_("Library of Congress number (LCCN)"),
            actions={"fill": _("Fill in LCCN"), "check": _("Check LCCN")},
            questions={
                "fill": _("Does this Library of Congress record describe the edition on this page?"),
            },
            notes=[
                Note(
                    _("Hyphenated and padded forms are the same number: 75-425165 and 75425165. Paste either; Open Library stores the padded form."),
                    LCCN_SPEC,
                ),
            ],
            traps=[
                Trap(_("The number belongs to a different printing. Search results lead with the best-known one, not with yours."), "match"),
                Trap(_("The number is already on another edition of this work, which means one of the two records is wrong."), "collision"),
                Trap(_("Pasting the web address instead of the number itself."), "format"),
                Trap(_("The Library of Congress filed several printings under one number. If the year and publisher match, that is as far as anyone can check.")),
            ],
            other_label=_("A different LCCN I found myself"),
            other_placeholder=_("For example 75425165"),
        ),
        "oclc_numbers": Playbook(
            field="oclc_numbers",
            label=_("OCLC/WorldCat number"),
            actions={"fill": _("Fill in OCLC number"), "check": _("Check OCLC number")},
            questions={
                "fill": _("Does this WorldCat record describe the edition on this page?"),
            },
            why=_(
                "The OCLC number is how libraries the world over refer to one catalogued edition. "
                "It is one of the few fields Open Library uses to find duplicates of this book when new records arrive."
            ),
            notes=[
                Note(
                    _("The prefixes ocm, ocn, on and (OCoLC) are padding added by library systems, not part of the number. ocm00047810608 is 47810608."),
                    OCLC_SPEC,
                ),
            ],
            traps=[
                Trap(_("The number belongs to a different printing, a book club edition, or the ebook rather than the print copy."), "match"),
                Trap(_("The number is already on another edition of this work, which means one of the two records is wrong."), "collision"),
                Trap(_("Pasting the web address, or leaving the ocm/ocn prefix on."), "format"),
                Trap(_("WorldCat sometimes files several printings under one record, so an exact year match is the thing to look for.")),
            ],
            other_label=_("A different OCLC number I found myself"),
            other_placeholder=_("Digits only, for example 47810608"),
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
