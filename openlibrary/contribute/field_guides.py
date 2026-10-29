"""One field guide per field: the question, where to look it up, and the conventions to follow.

The page links to each source on the edition's ISBN; Open Library fetches nothing from them.
"""

from dataclasses import dataclass
from dataclasses import field as dc_field

from openlibrary.i18n import gettext as _

HELP_BASE = "https://openlibrary.org/help/faq/editing"
# Open Library's cover guidelines: which image belongs on an edition, and when to replace one.
COVER_GUIDELINES = f"{HELP_BASE}#picture"
# The Library of Congress and OCLC syntax rules Open Library's normalizers implement.
LCCN_SPEC = "https://www.loc.gov/marc/lccn-namespace.html"
OCLC_SPEC = "https://help.oclc.org/Librarian_Toolbox/Searching_WorldCat_Indexes/Bibliographic_records/OCLC_control_number"

# Search pages opened on an ISBN-13.
WORLDCAT = "https://search.worldcat.org/search?q=bn:{isbn}"
GOOGLE_BOOKS = "https://books.google.com/books?vid=ISBN{isbn}"
AMAZON = "https://www.amazon.com/s?k={isbn}"
LOC = "https://catalog.loc.gov/vwebv/search?searchArg={isbn}&searchCode=GKEY%5E*&searchType=0"
BETTER_WORLD_BOOKS = "https://www.betterworldbooks.com/product/detail/{isbn}"
# A book's Amazon product id is its ISBN-10; L is the large image. A 1x1 GIF when Amazon has none.
AMAZON_COVER = "https://m.media-amazon.com/images/P/{isbn10}.01.L.jpg"


@dataclass(frozen=True)
class GuidelineNote:
    text: str
    href: str | None = None


@dataclass(frozen=True)
class LookupSource:
    label: str
    url: str  # may hold an {isbn} placeholder


@dataclass(frozen=True)
class FieldGuide:
    field: str
    label: str
    action: str
    question: str
    how: str  # where to look and what to copy; a blank line starts a new paragraph
    sources: list[LookupSource] = dc_field(default_factory=list)
    why: str = ""
    show_siblings: bool = False  # set only for fields where other editions' values help
    sibling_hint: str = ""
    suggest_from_siblings: bool = False  # offer the other editions' values as one-click answers
    notes: list[GuidelineNote] = dc_field(default_factory=list)
    traps: list[str] = dc_field(default_factory=list)
    placeholder: str = ""
    input_type: str = "text"
    check: str = ""  # what to look at before saving, shown under the answer
    confirm: str = ""  # a checkbox the answer can't be saved without
    choices: str = ""  # a tag type: the answer is one of its tags, picked rather than typed
    not_found: str = ""  # the honest exit's label when it isn't "I couldn't find it"
    quick_next: bool = False  # choices only: clicking the picked row again saves and moves on


def get_field_guides() -> dict[str, FieldGuide]:
    worldcat = LookupSource(_("WorldCat"), WORLDCAT)
    google = LookupSource(_("Google Books"), GOOGLE_BOOKS)
    amazon = LookupSource(_("Amazon"), AMAZON)
    loc = LookupSource(_("Library of Congress"), LOC)
    return {
        "covers": FieldGuide(
            field="covers",
            label=_("Cover"),
            action=_("Add a cover"),
            question=_("Can you find this edition's cover?"),
            how=_(
                "Look the ISBN up on Google Books, Amazon or Better World Books and save the front cover image. "
                "Check that the title, author and publisher on the image match this edition, then upload it here."
            ),
            sources=[google, amazon, LookupSource(_("Better World Books"), BETTER_WORLD_BOOKS)],
            notes=[
                GuidelineNote(
                    _("Upload the cover only, flat and in full: no photos of the book on a table, no 3D mockups, no store badges or watermarks."),
                    COVER_GUIDELINES,
                ),
            ],
            traps=[
                _("The cover belongs to another edition. A paperback, a reissue or a translation usually has a different cover; check the publisher."),
                _("Making a cover yourself. If you can't find the real one, leave it for someone who can."),
            ],
            input_type="file",
            check=_("Look for anything that doesn't fit this edition, such as “Graphic Novel”, “Movie tie-in” or a title in another language."),
        ),
        "languages": FieldGuide(
            field="languages",
            label=_("Language"),
            action=_("Fill in language"),
            question=_("What language is this edition written in?"),
            how=_("Look the ISBN up in WorldCat or Google Books; both list the language of the text. The title page and cover tell you too."),
            sources=[worldcat, google],
            show_siblings=True,
            suggest_from_siblings=True,
            sibling_hint=_("Editions of a work usually share a language, but a translation won't. Check this edition's own text."),
            notes=[
                GuidelineNote(
                    _("Record the language of the text, not the language of the title page. A translation is in the language it was translated into."),
                    f"{HELP_BASE}#edit-metadata-language",
                ),
            ],
            placeholder=_("For example English"),
        ),
        "number_of_pages": FieldGuide(
            field="number_of_pages",
            label=_("Page count"),
            action=_("Fill in page count"),
            question=_("How many pages does this edition have?"),
            how=_(
                "WorldCat lists the page count in the record's description. Google Books calls it Length. "
                "Make sure the record is for this ISBN, not another printing."
            ),
            sources=[worldcat, google, amazon],
            notes=[
                GuidelineNote(
                    _(
                        "Catalogs count front matter differently, so numbers within a few pages of each other are the same count. "
                        "Use the last numbered page of the main text."
                    ),
                    f"{HELP_BASE}#pages",
                ),
            ],
            placeholder=_("For example 320"),
            input_type="number",
        ),
        # A judgment about the work: answer from knowing the book, or look it up.
        "literary_form": FieldGuide(
            field="literary_form",
            label=_("Literary form"),
            action=_("Mark fiction or nonfiction"),
            question=_("Is this book fiction or nonfiction?"),
            how=_("If you know the book, answer from what you know. If you don't, look it up."),
            sources=[google, worldcat],
            notes=[
                GuidelineNote(_("Nonfiction can read like a story. A memoir that bends the truth is still nonfiction: it is presented as fact.")),
                GuidelineNote(_("Anthologies and collections take the form of what's inside. A book of essays about novels is nonfiction.")),
            ],
            choices="literary_form",
            not_found=_("Not sure"),
            # An easy call most of the time, so the answer can double as the save.
            quick_next=True,
        ),
        "publishers": FieldGuide(
            field="publishers",
            label=_("Publisher"),
            action=_("Fill in publisher"),
            question=_("Who published this edition?"),
            how=_("The imprint is printed on the title page and the spine. WorldCat and the Library of Congress list it under Publisher."),
            sources=[worldcat, loc, google],
            show_siblings=True,
            notes=[
                GuidelineNote(
                    _("Open Library records the imprint printed on the book, not the parent company. Anchor Books, not Penguin Random House."),
                    f"{HELP_BASE}#publisher",
                ),
            ],
            placeholder=_("Publisher as printed"),
        ),
        "lccn": FieldGuide(
            field="lccn",
            label=_("Library of Congress number (LCCN)"),
            action=_("Fill in LCCN"),
            question=_("What is this edition's Library of Congress number?"),
            how=_(
                "Search the Library of Congress catalog for this ISBN. Open the record whose publisher and edition match this one, "
                "and copy the number shown as LCCN. A paperback or later printing can show a different year and still be the same record."
            ),
            sources=[loc],
            notes=[
                GuidelineNote(
                    _("Hyphenated and padded forms are the same number: 75-425165 and 75425165. Paste either; Open Library stores the padded form."),
                    LCCN_SPEC,
                ),
            ],
            traps=[
                _("The number belongs to a different edition: another publisher's, a revised edition, a translation or the ebook. Each has its own record."),
                _(
                    "The number is already on another edition of this work. That's right when it's the hardcover, paperback or a later printing "
                    "from the same publisher; a different publisher or a revised edition means one of the two records is wrong."
                ),
                _("Pasting the web address instead of the number itself."),
            ],
            placeholder=_("For example 75425165"),
            confirm=_("I opened the record and its publisher and edition match this one."),
        ),
        "oclc_numbers": FieldGuide(
            field="oclc_numbers",
            label=_("OCLC/WorldCat number"),
            action=_("Fill in OCLC number"),
            question=_("What is this edition's WorldCat (OCLC) number?"),
            how=_(
                "Search WorldCat for this ISBN. Open the print record whose publisher and edition match this one, and copy the number shown as OCLC Number. "
                "A paperback or later printing can show a different year and still be the same record."
            ),
            sources=[worldcat],
            why=_(
                "The OCLC number is how libraries the world over refer to one catalogued edition. "
                "It is one of the few fields Open Library uses to find duplicates of this book when new records arrive."
            ),
            notes=[
                GuidelineNote(
                    _("The prefixes ocm, ocn, on and (OCoLC) are padding added by library systems, not part of the number. ocm00047810608 is 47810608."),
                    OCLC_SPEC,
                ),
                GuidelineNote(_("WorldCat sometimes lists one edition more than once. Any of those numbers is right; OCLC merges them over time.")),
            ],
            traps=[
                _("The number belongs to a different record: the ebook, another publisher's edition, a revised edition, large print or a translation."),
                _(
                    "The number is already on another edition of this work. That's right when it's the hardcover, paperback or a later printing "
                    "from the same publisher; a different publisher or a revised edition means one of the two records is wrong."
                ),
                _("Pasting the web address, or leaving the ocm/ocn prefix on."),
            ],
            placeholder=_("Digits only, for example 47810608"),
            confirm=_("I opened a print record and its publisher and edition match this one."),
        ),
    }


def build_link_outs(field_guide: FieldGuide, isbn13: str | None) -> list[LookupSource]:
    """The field guide's sources, opened on this ISBN."""
    if not isbn13:
        return []
    return [LookupSource(s.label, s.url.format(isbn=isbn13)) for s in field_guide.sources]
