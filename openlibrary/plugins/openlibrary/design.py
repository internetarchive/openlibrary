"""The Open Library design system docs at /developers/design.

Five sections share one shell: Principles (the design philosophy), Components
(the landing section), Foundations (design tokens), Icons, and Playground. Each section is one long browsable page
— the goal is density, so an engineer can scan everything available before
picking something.

Three things here are derived rather than hand-maintained, which is what keeps
the page from drifting as the system grows:

  * Token documentation is parsed out of the token CSS (see design_tokens.py).
  * Lit component API tables come from the Custom Elements Manifest.
  * The sidebar and the component sections are both built from COMPONENTS below,
    so adding a component means one registry row plus one partial.
"""

import json
import logging
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from infogami.utils import delegate
from infogami.utils.view import render_template
from openlibrary import accounts
from openlibrary.core.bookshelves import Bookshelves
from openlibrary.core.bookshelves_events import BookshelfEvent, BookshelvesEvents
from openlibrary.core.ratings import Ratings
from openlibrary.plugins.openlibrary.design_tokens import load_token_categories
from openlibrary.utils import extract_numeric_id_from_olid

logger = logging.getLogger("openlibrary.design")

# Custom Elements Manifest generated from JSDoc on the Lit components by
# `npx cem analyze` (see custom-elements-manifest.config.mjs), which
# `make lit-components` runs. Generated, not committed — see .gitignore.
MANIFEST_PATH = Path(__file__).parents[2] / "components" / "lit" / "custom-elements.json"


@dataclass(frozen=True)
class Section:
    """One tab of the design system docs.

    ``has_code`` gates the show-code toggle: only the component write-ups carry
    snippets, so the other sections would render a control that toggles nothing.
    ``has_nav`` gates the contents sidebar; a short section is just scrolled.
    """

    id: str
    title: str
    has_code: bool = False
    has_nav: bool = True


SECTIONS = (
    Section("principles", "Principles", has_nav=False),
    Section("components", "Components", has_code=True),
    Section("foundations", "Foundations"),
    Section("icons", "Icons", has_code=True),
    Section("playground", "Playground"),
)


@dataclass(frozen=True)
class Principle:
    """One entry on the Principles section.

    ``example`` is a scenario where the principle pulls against another
    reasonable choice — the point of the page is those, not the slogans. The
    figure for each row lives in principles.html.jinja, keyed by ``id``.
    """

    id: str
    title: str
    blurb: str
    example: str


PRINCIPLES = (
    Principle(
        "tools-before-brand",
        "Tools before brand",
        "We are building the workbench first and the storefront later. Every decision right now should make a control clearer, "
        "faster, or more consistent. Identity work is deferred, not rejected.",
        "A big illustrated hero on the home page would look great and is on-brand for a library. It also spends effort on the one "
        "page librarians spend the least time on, and introduces a visual language we haven't committed to.",
    ),
    Principle(
        "keep-the-paper",
        "Keep the paper",
        "Our palette comes from paper, and paper comes from books. The beige canvas is not sacred as a background, but it is the "
        "root of the color theme: every neutral, from the lightest raised surface to the darkest ink, descends from that warm "
        "family. The theme can keep evolving as long as it stays recognizably related to what came before.",
        "What visual recognition we have rests on a handful of cues, and the warm neutrals are the strongest of them. A returning "
        "user finds their way around a rearranged home page easily enough; a page that has gone cold reads as somewhere else "
        "before they read a word. That makes the canvas the cheapest thing to swap and the most expensive thing to lose.",
    ),
    Principle(
        "quiet-surface",
        "Quiet surface, quick hands",
        "Polished, not extravagant. Flat controls, one accent, muted status colors, no gradients, no ornament. The interface should "
        "be forgettable so the books and the work are not.",
        "A moment that deserves celebration, like finishing a reading goal or a big import. A quiet toast is on-principle and a "
        "little cold. A flourish is warm and off-principle.",
    ),
    Principle(
        "everything-answers-back",
        "Everything answers back",
        "A pointer landing, a key pressed, a click made: each gets an immediate, visible response. Hover snaps in with no "
        "transition. Press squeezes. Selection changes instantly. The site should feel like it is listening even when the server "
        "is slow.",
        "A soft hover fade looks more refined when you watch it in a prototype or a demo. Under your own cursor it reads as lag. "
        "We chose snap because it feels faster in the hand.",
    ),
    Principle(
        "never-hide-the-wait",
        "Never hide the wait",
        "Loading, saving, and progress are part of the UI, not a failure state. Every request over about 100 ms shows something: a "
        "spinner, a skeleton, or a progress bar. Slow and honest beats fast-looking and blank.",
        "A request that is usually 80 ms but sometimes 2 s. Showing a spinner every time flickers on the fast path. Delaying it "
        "leaves the slow path frozen. Pick a threshold and live with the flicker or the gap.",
    ),
    Principle(
        "motion-is-information",
        "Motion is information",
        "Animate only what changed: something entering, leaving, moving, or changing state. Durations are short, curves are "
        "decisive, exits are faster than entries. Reduced motion is honored everywhere.",
        "A subject page hero with a staged reveal would add atmosphere. It is also 600 ms of the user waiting to read. Editorial "
        "pages are the most tempting place to break this rule.",
    ),
    Principle(
        "dense-on-the-desk",
        "Dense on the desk",
        "Desktop is a workbench for people who spend hours here. Controls are compact, more fits per screen, secondary actions are "
        "one click away rather than buried. Mobile gets larger targets and simpler layouts, but desktop is not a stretched phone.",
        "44 px touch targets on desktop are safer for accessibility and worse for density. Our medium control is 32 px.",
    ),
    Principle(
        "keyboard-first-class",
        "Keyboard is a first-class pointer",
        "Editors and librarians live on the keyboard. Every control is reachable by Tab, every action has a visible focus ring, "
        "forms submit on Enter, and focus never gets lost inside a shadow root or an overlay.",
        "Keyboard shortcuts speed up power users and are invisible to everyone else. Adding them means also adding a way to "
        "discover them, which is more UI to design.",
    ),
    Principle(
        "one-way-to-say-it",
        "One way to say each thing",
        "One selected look, one hover mechanism, one icon set. When two components disagree, one of them is wrong. Fewer patterns "
        "is the point, even when the second pattern is nicer.",
        "A purpose-built component like the scorecard looks better tuned than the shared one. Every bespoke piece is a debt the "
        "next person inherits. Allow it only when the shared component can't be extended.",
    ),
    Principle(
        "nothing-shifts",
        "Nothing shifts",
        "Layout stability is a feature. No weight change on hover or selection, tabular numbers for anything that counts, reserved "
        "space for content that is loading. A page that jumps feels broken even when it isn't.",
        "Reserving space for a region that might come back empty leaves a hole. Not reserving it means a jump when it fills. For "
        "carousels and availability data we usually can't know in advance.",
    ),
    Principle(
        "accessible-is-the-floor",
        "Accessible is the floor",
        "Contrast is tested in CI. Text is at least 4.5:1, control edges at least 3:1, motion respects the OS setting, and "
        "semantics come from native elements first.",
        "Hairline dividers between result rows look better below 3:1. At full weight the list reads as a spreadsheet. We allow "
        "extra-subtle for repeating separators, and someone will reach for it on a control border.",
    ),
)


@dataclass(frozen=True)
class Tension:
    """Two principles that pull against each other, and how we resolve it so far."""

    title: str
    body: str


TENSIONS = (
    Tension(
        "Cozy vs. snappy",
        "Warm palette and serif titles pull toward slow and soft. Instant hover and short durations pull toward brisk. Color and "
        "type carry the warmth, motion carries the speed. Never soften motion to match the palette.",
    ),
    Tension(
        "Density vs. accessibility",
        "Compact controls and hairline dividers serve the librarian's screen. Contrast is non-negotiable and tested; size floors differ by pointer type.",
    ),
    Tension(
        "Honesty vs. calm",
        "Showing every wait and every state adds visual activity. The quiet surface wants less. Feedback is local and small, never "
        "page-wide unless the page itself is what's loading.",
    ),
    Tension(
        "One system vs. the special case",
        "Editorial pages, celebrations, and purpose-built tools all want exceptions. Exceptions are allowed only where the shared component can't be extended.",
    ),
)


@dataclass(frozen=True)
class Component:
    """A registry row. Drives the sidebar and the section order.

    ``partial`` names a Jinja template defining a ``demos()`` macro holding the
    component's write-up. A row with no ``tag`` is a class-based CSS component,
    which has no manifest entry and so renders without an API table. Clear
    ``api_table`` for a row that is documented in full somewhere else.
    """

    id: str
    title: str
    partial: str
    group: str = ""
    tag: str = ""
    avoid: str = ""
    api_table: bool = True


COMPONENTS = (
    # --- Actions ---------------------------------------------------------
    Component(
        "button",
        "Button",
        "design/components/button.html.jinja",
        group="Actions",
        tag="ol-button",
        avoid="For a state that stays on or off, use Toggle. For a filter that can be removed, use Chip.",
    ),
    Component(
        "toggle",
        "Toggle",
        "design/components/toggle.html.jinja",
        group="Actions",
        tag="ol-toggle",
        avoid="For picking one of several options use Segmented Control.",
    ),
    Component(
        "segmented-control",
        "Segmented Control",
        "design/components/segmented-control.html.jinja",
        group="Actions",
        tag="ol-segmented-control",
        avoid="More than about four options belong in a Select Popover.",
    ),
    Component(
        "chip",
        "Chip",
        "design/components/chip.html.jinja",
        group="Actions",
        tag="ol-chip",
        avoid="A chip is a removable or selectable filter. A one-shot action is a Button.",
    ),
    Component(
        "chip-group",
        "Chip Group",
        "design/components/chip-group.html.jinja",
        group="Actions",
        tag="ol-chip-group",
        avoid="Only for laying out Chips; don't wrap other controls in it.",
    ),
    Component(
        "pagination",
        "Pagination",
        "design/components/pagination.html.jinja",
        group="Actions",
        tag="ol-pagination",
        avoid="For an open-ended feed, load more in place instead of paging.",
    ),
    # --- Overlays --------------------------------------------------------
    Component(
        "tooltip",
        "Tooltip",
        "design/components/tooltip.html.jinja",
        group="Overlays",
        tag="ol-tooltip",
        avoid="Never put essential information or interactive content in a tooltip.",
    ),
    Component(
        "popover",
        "Popover",
        "design/components/popover.html.jinja",
        group="Overlays",
        tag="ol-popover",
        avoid="Use the composed variants (Select, Options, Menu) before a bare Popover; reserve it for custom panel content.",
    ),
    Component(
        "select-popover",
        "Select Popover",
        "design/components/select-popover.html.jinja",
        group="Overlays",
        tag="ol-select-popover",
        avoid="For a single choice use Options Popover; for four or fewer choices use Segmented Control.",
    ),
    Component(
        "options-popover",
        "Options Popover",
        "design/components/options-popover.html.jinja",
        group="Overlays",
        tag="ol-options-popover",
        avoid="Multiple selections belong in a Select Popover.",
    ),
    Component(
        "menu-popover",
        "Menu Popover",
        "design/components/menu-popover.html.jinja",
        group="Overlays",
        tag="ol-menu-popover",
        avoid="A choice that is read or submitted later is a value, not an action — use Options Popover.",
    ),
    Component(
        "dialog",
        "Dialog",
        "design/components/dialog.html.jinja",
        group="Overlays",
        tag="ol-dialog",
        avoid="For a task with its own scrolling content, use Drawer. For a passive message, use Toast or Banner.",
    ),
    Component(
        "drawer",
        "Drawer",
        "design/components/drawer.html.jinja",
        group="Overlays",
        tag="ol-drawer",
        avoid="A centered interruption is a Dialog. A panel anchored to its trigger is a Popover.",
    ),
    # --- Feedback --------------------------------------------------------
    Component(
        "toast",
        "Toast",
        "design/components/toast.html.jinja",
        group="Feedback",
        tag="ol-toast",
        avoid="Anything the reader must act on belongs in a Dialog or a Banner.",
    ),
    Component(
        "banner",
        "Banner",
        "design/components/banner.html.jinja",
        group="Feedback",
        tag="ol-banner",
        avoid="Page-level and persistent. For confirmation of an action the user just took, use Toast.",
    ),
    Component(
        "message",
        "Message",
        "design/components/message.html.jinja",
        group="Feedback",
        avoid="Inline, next to the thing it describes. For page-level notices use Banner.",
    ),
    Component(
        "scorecard",
        "Scorecard",
        "design/components/scorecard.html.jinja",
        group="Feedback",
        tag="ol-scorecard",
        avoid="Purpose-built for the book-quality score; don't repurpose it as a generic gauge.",
    ),
    # --- Content ---------------------------------------------------------
    Component(
        "carousel",
        "Carousel",
        "design/components/carousel.html.jinja",
        group="Content",
        tag="ol-carousel",
        avoid="For fewer than about six items, lay them out in a row instead.",
    ),
    Component(
        "read-more",
        "Read More",
        "design/components/read-more.html.jinja",
        group="Content",
        tag="ol-read-more",
        avoid="Only for prose. Don't hide controls or lists behind it.",
    ),
    Component(
        "markdown-editor",
        "Markdown Editor",
        "design/components/markdown-editor.html.jinja",
        group="Content",
        tag="ol-markdown-editor",
        avoid="For a plain text field use <textarea>; this is for Markdown bodies only.",
    ),
    # A stub on purpose: icons have a section of their own, and this row exists
    # so someone scanning the component list finds them rather than concluding
    # there is nothing.
    Component(
        "icon",
        "Icon",
        "design/components/icon.html.jinja",
        group="Content",
        tag="ol-icon",
        avoid="Only for icons from the set; don't use it to embed arbitrary SVG.",
        api_table=False,
    ),
    # --- Books -----------------------------------------------------------
    # The domain layer: everything here knows what a book is. Generic pieces
    # they compose (Button, Popover) stay in their own sections.
    Component(
        "book-cover",
        "Book Cover",
        "design/components/book-cover.html.jinja",
        group="Books",
        tag="ol-book-cover",
    ),
    Component(
        "shelf-button",
        "Shelf Button",
        "design/components/shelf-button.html.jinja",
        group="Books",
        tag="ol-shelf-button",
    ),
    Component(
        "shelf-actions",
        "Shelf Actions",
        "design/components/shelf-actions.html.jinja",
        group="Books",
        tag="ol-shelf-actions",
    ),
)

# Icon sources, one SVG per icon, grouped into folders by provenance. The file
# names are the icon names, so the gallery globs them rather than reading a
# generated list that could drift.
ICON_SRC_DIR = Path(__file__).parents[3] / "static" / "icons" / "src"


def _clean_default(value):
    """Normalize a manifest default for display. The analyzer emits the literal
    strings "null"/"undefined" for fields left unset in the constructor; show
    those as blank (an em dash) rather than a misleading default value."""
    if value in {None, "null", "undefined"}:
        return ""
    return value


def _clean_declaration(decl):
    """Reduce a Custom Elements Manifest declaration to the API the design page
    renders: public properties, events, slots, CSS custom properties, CSS parts."""
    properties = [
        {
            "name": member["name"],
            "attribute": member.get("attribute", ""),
            "type": (member.get("type") or {}).get("text", ""),
            "default": _clean_default(member.get("default")),
            "description": member.get("description", ""),
        }
        for member in decl.get("members", [])
        if member.get("kind") == "field"
        and member.get("privacy", "public") == "public"
        and not member["name"].startswith("_")
        # JSDoc is the source of truth: only surface documented properties (`@prop`).
        # Undocumented class fields carry no description — including Lit `state: true`
        # reactive state, which the analyzer can't reliably tell apart from public
        # attributes — and are intentionally omitted.
        and member.get("description")
    ]
    events = [
        {
            "name": event["name"],
            "type": (event.get("type") or {}).get("text", ""),
            "description": event.get("description", ""),
        }
        for event in decl.get("events", [])
    ]
    slots = [{"name": slot.get("name", ""), "description": slot.get("description", "")} for slot in decl.get("slots", [])]
    css_properties = [
        {
            "name": prop["name"],
            "default": _clean_default(prop.get("default")),
            "description": prop.get("description", ""),
        }
        for prop in decl.get("cssProperties", [])
    ]
    css_parts = [{"name": part["name"], "description": part.get("description", "")} for part in decl.get("cssParts", [])]
    return {
        "tagName": decl.get("tagName"),
        "properties": properties,
        "events": events,
        "slots": slots,
        "cssProperties": css_properties,
        "cssParts": css_parts,
    }


@cache
def load_components():
    """Component API data by tag name, from the generated manifest.

    Cached: it's a build artifact, so it can't change without a restart. Returns
    empty if unreadable, leaving the live demos minus their API tables.
    """
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except OSError, ValueError:
        logger.warning(
            "Could not read Custom Elements Manifest at %s — the design page's API tables will be empty. Run `make lit-components` to generate it.",
            MANIFEST_PATH,
        )
        return {}
    components = {}
    for module in manifest.get("modules", []):
        for decl in module.get("declarations", []):
            if tag := decl.get("tagName"):
                components[tag] = _clean_declaration(decl)
    return components


@cache
def load_icons() -> list[str]:
    """The sorted icon names, taken from the source SVG file names.

    Cached because the set is fixed for the life of the process. A missing
    directory renders an empty gallery rather than 500ing.
    """
    if not (names := sorted(path.stem for path in ICON_SRC_DIR.glob("*/*.svg"))):
        logger.warning("No icon sources found at %s — the icon gallery will be empty.", ICON_SRC_DIR)
    return names


def _component_groups() -> tuple[tuple[str, list[Component]], ...]:
    """COMPONENTS bucketed by group, in registry order — Jinja's ``groupby``
    sorts alphabetically, scrambling the deliberate ordering."""
    grouped: dict[str, list[Component]] = {}
    for component in COMPONENTS:
        grouped.setdefault(component.group, []).append(component)
    return tuple(grouped.items())


# Derived from a module constant, so it is one too rather than per-request work.
COMPONENT_GROUPS = _component_groups()


@dataclass
class DesignContext:
    """Everything the shell and one section's body need to render."""

    section: Section
    sections: tuple[Section, ...] = SECTIONS
    groups: tuple[tuple[str, list[Component]], ...] = COMPONENT_GROUPS
    principles: tuple[Principle, ...] = PRINCIPLES
    tensions: tuple[Tension, ...] = TENSIONS
    api: dict = field(default_factory=dict)
    token_categories: list = field(default_factory=list)
    # The book demos write to the signed-in reader's real reading log and
    # lists, so they need their key; empty sends the demo to log in instead.
    user_key: str = ""
    # Their shelf/rating/check-in for the demo works, keyed by OLID, so the
    # demos open on real state without a client fetch:
    # {"OL69612W": {"shelf": 3, "rating": 4, "read_date": "2026-08", "event_id": 7}}.
    reading_state: dict = field(default_factory=dict)
    icons: list[str] = field(default_factory=list)


# The works the book demos read and write; must match the demo templates.
DEMO_WORK_OLIDS = ("OL69612W", "OL27448W")


def demo_reading_state(username: str) -> dict[str, dict]:
    """The reader's shelf, rating, and last finish date for each demo work, keyed by OLID."""
    numeric_ids = [int(extract_numeric_id_from_olid(olid)) for olid in DEMO_WORK_OLIDS]
    shelves = {row.work_id: row.bookshelf_id for row in Bookshelves.get_users_read_status_of_works(username, numeric_ids)}
    ratings = Ratings.get_users_ratings_of_works(username, numeric_ids)
    check_ins = {work_id: BookshelvesEvents.get_latest_event_date(username, work_id, BookshelfEvent.FINISH) for work_id in numeric_ids}
    return {
        olid: {
            "shelf": shelves.get(work_id),
            "rating": ratings.get(work_id),
            "read_date": check_ins[work_id]["event_date"] if check_ins[work_id] else None,
            "event_id": check_ins[work_id]["id"] if check_ins[work_id] else None,
        }
        for olid, work_id in zip(DEMO_WORK_OLIDS, numeric_ids)
    }


def build_context(section_id: str) -> DesignContext:
    section = next(candidate for candidate in SECTIONS if candidate.id == section_id)
    user = accounts.get_current_user()
    context = DesignContext(section=section, user_key=user.key if user else "")
    if section_id == "foundations":
        context.token_categories = load_token_categories()
    elif section_id == "components":
        # Playground renders no API tables, so it pays for none.
        context.api = load_components()
        if user:
            context.reading_state = demo_reading_state(user.key.split("/")[-1])
    elif section_id == "icons":
        context.icons = load_icons()
        # <ol-icon> is one of three ways to draw a glyph, so the Icons section
        # carries its API table too — the Components row only points here.
        context.api = load_components()
    return context


class design(delegate.page):
    path = "/developers/design"

    def GET(self):
        return render_template("design", build_context("components"))


class design_section(delegate.page):
    path = r"/developers/design/(principles|components|foundations|icons|playground)"

    def GET(self, section_id):
        return render_template("design", build_context(section_id))


def setup():
    pass
