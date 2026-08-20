"""The Open Library design system docs at /developers/design.

Three sections share one shell: Components (the landing section), Foundations
(design tokens), and Playground. Each section is one long browsable page — the
goal is density, so an engineer can scan everything available before picking
something.

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
from openlibrary.plugins.openlibrary.design_tokens import load_token_categories

logger = logging.getLogger("openlibrary.design")

# Custom Elements Manifest generated from JSDoc on the Lit components by
# `npx cem analyze` (see custom-elements-manifest.config.mjs), which
# `make lit-components` runs. Generated, not committed — see .gitignore.
MANIFEST_PATH = Path(__file__).parents[2] / "components" / "lit" / "custom-elements.json"
CSS_COMPONENTS_DIR = Path(__file__).parents[3] / "static" / "css" / "components"


@dataclass(frozen=True)
class Section:
    """One tab of the design system docs.

    ``has_code`` gates the show-code toggle: only the component write-ups carry
    snippets, so the other sections would render a control that toggles nothing.
    """

    id: str
    title: str
    has_code: bool = False


SECTIONS = (
    Section("components", "Components", has_code=True),
    Section("foundations", "Foundations"),
    Section("playground", "Playground"),
)


@dataclass(frozen=True)
class Component:
    """A registry row. Drives the sidebar and the section order.

    ``partial`` names a Jinja template defining a ``demos()`` macro holding the
    component's write-up. A row with no ``tag`` is a class-based CSS component,
    which has no manifest entry and so renders without an API table.
    """

    id: str
    title: str
    use_when: str
    partial: str
    group: str = ""
    tag: str = ""
    avoid: str = ""
    # Which files under static/css/components/ this row documents — a Lit
    # component's own stylesheet, or the class definitions behind a CSS one.
    # Used for the coverage report, so the page can show its gaps.
    css_files: tuple[str, ...] = ()


COMPONENTS = (
    # --- Actions ---------------------------------------------------------
    Component(
        "button",
        "Button",
        "Any clickable action. The default choice — reach for this before a raw <button>.",
        "design/components/button.html.jinja",
        group="Actions",
        tag="ol-button",
        css_files=("ol-button",),
    ),
    Component(
        "toggle",
        "Toggle",
        "Flipping a single setting on or off, applied immediately.",
        "design/components/toggle.html.jinja",
        group="Actions",
        tag="ol-toggle",
        avoid="For picking one of several options use Segmented Control.",
    ),
    Component(
        "segmented-control",
        "Segmented Control",
        "Choosing one of two to four mutually exclusive views, all labels visible at once.",
        "design/components/segmented-control.html.jinja",
        group="Actions",
        tag="ol-segmented-control",
        avoid="More than about four options belong in a Select Popover.",
    ),
    Component(
        "chip",
        "Chip",
        "A compact, pill-shaped tag or filter, often colored by the kind of thing it names.",
        "design/components/chip.html.jinja",
        group="Actions",
        tag="ol-chip",
    ),
    Component(
        "chip-group",
        "Chip Group",
        "Laying out a wrapping row of chips with consistent spacing.",
        "design/components/chip-group.html.jinja",
        group="Actions",
        tag="ol-chip-group",
    ),
    Component(
        "pagination",
        "Pagination",
        "Moving through a paged result set, by page number or by arrows alone.",
        "design/components/pagination.html.jinja",
        group="Actions",
        tag="ol-pagination",
    ),
    # --- Overlays --------------------------------------------------------
    Component(
        "tooltip",
        "Tooltip",
        "A short, non-essential hint shown on hover or focus.",
        "design/components/tooltip.html.jinja",
        group="Overlays",
        tag="ol-tooltip",
        avoid="Never put essential information or interactive content in a tooltip.",
    ),
    Component(
        "popover",
        "Popover",
        "Arbitrary content anchored to a trigger — menus, forms, rich detail.",
        "design/components/popover.html.jinja",
        group="Overlays",
        tag="ol-popover",
    ),
    Component(
        "select-popover",
        "Select Popover",
        "Picking several options from a long, optionally searchable list.",
        "design/components/select-popover.html.jinja",
        group="Overlays",
        tag="ol-select-popover",
    ),
    Component(
        "options-popover",
        "Options Popover",
        "Picking exactly one option from a short list, like a sort order.",
        "design/components/options-popover.html.jinja",
        group="Overlays",
        tag="ol-options-popover",
    ),
    Component(
        "menu-popover",
        "Menu Popover",
        "Acting on one of a short list of choices — a sort menu, or anything that navigates.",
        "design/components/menu-popover.html.jinja",
        group="Overlays",
        tag="ol-menu-popover",
        avoid="A choice that is read or submitted later is a value, not an action — use Options Popover.",
    ),
    Component(
        "dialog",
        "Dialog",
        "An interruption that must be dealt with before the page continues.",
        "design/components/dialog.html.jinja",
        group="Overlays",
        tag="ol-dialog",
    ),
    # --- Feedback --------------------------------------------------------
    Component(
        "toast",
        "Toast",
        "Confirming that something happened, without interrupting the reader.",
        "design/components/toast.html.jinja",
        group="Feedback",
        tag="ol-toast",
        avoid="Anything the reader must act on belongs in a Dialog or a Banner.",
    ),
    Component(
        "banner",
        "Banner",
        "A persistent, page-level announcement or call to action.",
        "design/components/banner.html.jinja",
        group="Feedback",
        tag="ol-banner",
    ),
    Component(
        "message",
        "Message",
        "Inline status next to the thing it describes — info, success, warning, error.",
        "design/components/message.html.jinja",
        group="Feedback",
        css_files=("ol-message", "flash-messages"),
    ),
    Component(
        "scorecard",
        "Scorecard",
        "Breaking a quality score into the checks that produced it.",
        "design/components/scorecard.html.jinja",
        group="Feedback",
        tag="ol-scorecard",
    ),
    # --- Content ---------------------------------------------------------
    Component(
        "carousel",
        "Carousel",
        "A horizontal, paged row of items — book covers, cards, shelves.",
        "design/components/carousel.html.jinja",
        group="Content",
        tag="ol-carousel",
    ),
    Component(
        "books-display",
        "Books Display",
        "A titled set of books for a query, switchable between a covers carousel and a list.",
        "design/components/books-display.html.jinja",
        group="Content",
        tag="ol-books-display",
    ),
    Component(
        "book-actions",
        "Book Actions",
        "Per-book shelf, rating and add-to-list actions in a popover.",
        "design/components/book-actions.html.jinja",
        group="Content",
        tag="ol-book-actions",
    ),
    Component(
        "read-more",
        "Read More",
        "Truncating long prose to a fixed height or line count, expandable in place.",
        "design/components/read-more.html.jinja",
        group="Content",
        tag="ol-read-more",
    ),
    Component(
        "markdown-editor",
        "Markdown Editor",
        "Rich editing over a plain <textarea> that stays the source of truth.",
        "design/components/markdown-editor.html.jinja",
        group="Content",
        tag="ol-markdown-editor",
    ),
)

# CSS files that document nothing reusable: page-specific styles, vendor
# overrides, and layout shims. Excluded from the coverage report so the
# "undocumented" list stays a real to-do list rather than permanent noise.
NOT_COMPONENTS = frozenset(
    {
        "admin-table",
        "chart",
        "chart-stats",
        "diff",
        "donate",
        "edit-toolbar",
        "edit-toolbar--tablet",
        "footer",
        "header",
        "header-bar",
        "header-bar--desktop",
        "header-bar--js",
        "header-bar--tablet",
        "jquery.autocomplete",
        "librarian-dashboard",
        "manage-covers",
        "merge-form",
        "merge-request-table",
        "metadata-form",
        "mybooks",
        "mybooks-details",
        "mybooks-dropper",
        "mybooks-list",
        "mybooks-menu",
        "observationStats",
        "pd-dashboard",
        "preview",
        "readerStats",
        "readinglog-stats",
        "team",
        "throbber",
        "ui-dialog",
        "ui-tabs",
        "work--tablet",
    }
)

# Legacy class-based components, deliberately undocumented: a write-up would
# only advertise what the web components replaced. Excluded like NOT_COMPONENTS.
LEGACY_CSS = frozenset(
    {
        "buttonBtn",
        "buttonCta",
        "buttonGhost",
        "buttonLink",
        "buttonsAndLinks",
        "link-box",
        "loading-indicator",
        "widget-box",
    }
)


def _clean_default(value):
    """Normalize a manifest default for display. The analyzer emits the literal
    strings "null"/"undefined" for fields left unset in the constructor; show
    those as blank (an em dash) rather than a misleading default value."""
    if value in (None, "null", "undefined"):
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
def undocumented_css_components() -> list[str]:
    """CSS component files that no registry row covers, so the page can report
    its own coverage gaps instead of implying the list is complete."""
    documented = {name for component in COMPONENTS for name in component.css_files}
    try:
        on_disk = {path.stem for path in CSS_COMPONENTS_DIR.glob("*.css")}
    except OSError:
        return []
    return sorted(on_disk - documented - NOT_COMPONENTS - LEGACY_CSS)


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
    api: dict = field(default_factory=dict)
    token_categories: list = field(default_factory=list)
    undocumented: list[str] = field(default_factory=list)
    # The book demos write to the signed-in reader's real reading log and
    # lists, so they need their key; empty sends the demo to log in instead.
    user_key: str = ""


def build_context(section_id: str) -> DesignContext:
    section = next(candidate for candidate in SECTIONS if candidate.id == section_id)
    user = accounts.get_current_user()
    context = DesignContext(section=section, user_key=user.key if user else "")
    if section_id == "foundations":
        context.token_categories = load_token_categories()
    elif section_id == "components":
        # Playground renders neither, so it pays for neither.
        context.api = load_components()
        context.undocumented = undocumented_css_components()
    return context


class design(delegate.page):
    path = "/developers/design"

    def GET(self):
        return render_template("design", build_context("components"))


class design_section(delegate.page):
    path = r"/developers/design/(components|foundations|playground)"

    def GET(self, section_id):
        return render_template("design", build_context(section_id))


def setup():
    pass
