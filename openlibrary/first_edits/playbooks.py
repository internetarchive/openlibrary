"""One playbook per field: the question in plain words, where to look it up,
and the conventions a librarian needs.

Open Library fetches nothing from these sources. The page links to them,
opened on the edition's ISBN, and says what to copy from each.

Copy lives here rather than in templates so the task template stays one
shape for every field. Strings are resolved per request for i18n.
"""

from dataclasses import dataclass
from dataclasses import field as dc_field

from openlibrary.i18n import gettext as _

HELP_BASE = "https://openlibrary.org/help/faq/editing"
# The Library of Congress and OCLC syntax rules Open Library's normalizers implement.
LCCN_SPEC = "https://www.loc.gov/marc/lccn-namespace.html"
OCLC_SPEC = "https://help.oclc.org/Librarian_Toolbox/Searching_WorldCat_Indexes/Bibliographic_records/OCLC_control_number"

# Search pages opened on an ISBN-13.
WORLDCAT = "https://search.worldcat.org/search?q=bn:{isbn}"
GOOGLE_BOOKS = "https://books.google.com/books?vid=ISBN{isbn}"
AMAZON = "https://www.amazon.com/s?k={isbn}"
LOC = "https://catalog.loc.gov/vwebv/search?searchArg={isbn}&searchCode=GKEY%5E*&searchType=0"


@dataclass(frozen=True)
class Note:
    text: str
    href: str | None = None


@dataclass(frozen=True)
class Source:
    label: str
    url: str  # template with {isbn}


@dataclass(frozen=True)
class LinkOut:
    label: str
    url: str


@dataclass(frozen=True)
class Playbook:
    field: str
    label: str
    action: str
    question: str
    how: str  # where to look and what to copy
    sources: list[Source] = dc_field(default_factory=list)
    why: str = ""
    notes: list[Note] = dc_field(default_factory=list)
    traps: list[str] = dc_field(default_factory=list)
    answer_label: str = ""
    placeholder: str = ""
    input_type: str = "text"


def get_playbooks() -> dict[str, Playbook]:
    worldcat = Source(_("WorldCat"), WORLDCAT)
    google = Source(_("Google Books"), GOOGLE_BOOKS)
    amazon = Source(_("Amazon"), AMAZON)
    loc = Source(_("Library of Congress"), LOC)
    return {
        "languages": Playbook(
            field="languages",
            label=_("Language"),
            action=_("Fill in language"),
            question=_("What language is this edition written in?"),
            how=_("Look the ISBN up in WorldCat or Google Books; both list the language of the text. The title page and cover tell you too."),
            sources=[worldcat, google],
            why=_("Language decides which readers find this edition in search and which editions get grouped together."),
            notes=[
                Note(
                    _("Record the language of the text, not the language of the title page. A translation is in the language it was translated into."),
                    f"{HELP_BASE}#edit-metadata-language",
                ),
            ],
            answer_label=_("Language"),
            placeholder=_("For example English"),
        ),
        "number_of_pages": Playbook(
            field="number_of_pages",
            label=_("Page count"),
            action=_("Fill in page count"),
            question=_("How many pages does this edition have?"),
            how=_(
                "WorldCat lists the page count in the record's description. Google Books calls it Length. Make sure the record is for this ISBN, not another printing."
            ),
            sources=[worldcat, google, amazon],
            notes=[
                Note(
                    _(
                        "Catalogs count front matter differently, so numbers within a few pages of each other are the same count. "
                        "Use the last numbered page of the main text."
                    ),
                    f"{HELP_BASE}#pages",
                ),
            ],
            answer_label=_("Number of pages"),
            placeholder=_("For example 320"),
            input_type="number",
        ),
        "publishers": Playbook(
            field="publishers",
            label=_("Publisher"),
            action=_("Fill in publisher"),
            question=_("Who published this edition?"),
            how=_("The imprint is printed on the title page and the spine. WorldCat and the Library of Congress list it under Publisher."),
            sources=[worldcat, loc, google],
            notes=[
                Note(
                    _("Open Library records the imprint printed on the book, not the parent company. Anchor Books, not Penguin Random House."),
                    f"{HELP_BASE}#publisher",
                ),
                Note(_("Match the spelling other editions of this work already use, so the publisher page stays in one piece."), f"{HELP_BASE}#publisher"),
            ],
            answer_label=_("Publisher"),
            placeholder=_("Publisher as printed"),
        ),
        "lccn": Playbook(
            field="lccn",
            label=_("Library of Congress number (LCCN)"),
            action=_("Fill in LCCN"),
            question=_("What is this edition's Library of Congress number?"),
            how=_(
                "Search the Library of Congress catalog for this ISBN. Open the record whose year and publisher match this edition, "
                "and copy the number shown as LCCN."
            ),
            sources=[loc],
            notes=[
                Note(
                    _("Hyphenated and padded forms are the same number: 75-425165 and 75425165. Paste either; Open Library stores the padded form."),
                    LCCN_SPEC,
                ),
            ],
            traps=[
                _("The number belongs to a different printing. Search results lead with the best-known one, not with yours."),
                _("The number is already on another edition of this work, which means one of the two records is wrong."),
                _("Pasting the web address instead of the number itself."),
            ],
            answer_label=_("LCCN"),
            placeholder=_("For example 75425165"),
        ),
        "oclc_numbers": Playbook(
            field="oclc_numbers",
            label=_("OCLC/WorldCat number"),
            action=_("Fill in OCLC number"),
            question=_("What is this edition's WorldCat (OCLC) number?"),
            how=_(
                "Search WorldCat for this ISBN. Open the record whose year, publisher and format match this edition, and copy the number shown as OCLC Number."
            ),
            sources=[worldcat],
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
                _("The number belongs to a different printing, a book club edition, or the ebook rather than the print copy."),
                _("The number is already on another edition of this work, which means one of the two records is wrong."),
                _("Pasting the web address, or leaving the ocm/ocn prefix on."),
            ],
            answer_label=_("OCLC number"),
            placeholder=_("Digits only, for example 47810608"),
        ),
    }


def link_outs(playbook: Playbook, isbn13: str | None) -> list[LinkOut]:
    """The playbook's sources, opened on this ISBN. Link only, never imported."""
    if not isbn13:
        return []
    return [LinkOut(s.label, s.url.format(isbn=isbn13)) for s in playbook.sources]
