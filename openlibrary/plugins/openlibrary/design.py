import json
import logging
from pathlib import Path
from urllib.parse import urlparse

import web

from infogami.utils import delegate
from infogami.utils.view import render_template, safeint
from openlibrary import accounts

logger = logging.getLogger("openlibrary.design")

# Custom Elements Manifest generated from JSDoc on the Lit components by
# `npx cem analyze` (see custom-elements-manifest.config.mjs), which
# `make lit-components` runs. Generated, not committed — see .gitignore.
MANIFEST_PATH = Path(__file__).parents[2] / "components" / "lit" / "custom-elements.json"


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


def load_components():
    """Index cleaned component API data by tag name from the generated manifest.

    Returns an empty dict if the manifest is missing or unreadable so the design
    page still renders its hand-written live demos, minus the API tables.
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


class home(delegate.page):
    path = "/developers/design"

    def GET(self):
        return render_template("design", load_components())


class activity_feed_gallery(delegate.page):
    """Side-by-side gallery of the activity feed's layout treatments.

    Temporary scaffolding for #10242 -- it exists so a design direction can be
    chosen from real, populated feed data rather than from mockups. It goes away
    with the nine unchosen variants once that decision is made.
    """

    path = "/developers/design/activity-feed"

    # Kept in step with FEED_VARIANTS in openlibrary/components/lit/OlSocialFeed.js.
    VARIANTS = (
        {"id": 1, "name": "Spec card", "blurb": "The reviewed design: patron and follow above the rule, book and actions below. Three up on desktop."},
        {"id": 2, "name": "Goodreads river", "blurb": "Full-width rows, one continuous sentence, generous cover, text actions."},
        {"id": 3, "name": "Cover tiles", "blurb": "The cover is the card. Caption strip overlays the bottom. Scrolls horizontally."},
        {"id": 4, "name": "Dense timeline", "blurb": "A rail of small avatars down the left. Maximum events per screen."},
        {"id": 5, "name": "Social thread", "blurb": "Bluesky shape: avatar column, prose, and the book as an embedded quote card."},
        {"id": 6, "name": "Magazine", "blurb": "Two-column masonry, big covers, serif titles, lots of air."},
        {"id": 7, "name": "Conversation", "blurb": "Activity as messages. Reads as live chatter rather than a log."},
        {"id": 8, "name": "Ticker", "blurb": "One compact line each. Sized to sit under a heading as a teaser strip."},
        {"id": 9, "name": "Editorial", "blurb": "Uppercase eyebrow, large type, almost no chrome. Actions on hover."},
        {"id": 10, "name": "People first", "blurb": "Grouped by patron: who they are, then a strip of what they touched."},
    )

    DEFAULT_API = "/api/internal/activity/feed.json"

    def GET(self):
        i = web.input(design=None, scope="auto", api=None)
        selected = safeint(i.design, 0)
        scope = i.scope if i.scope in ("auto", "public", "following") else "auto"
        user = accounts.get_current_user()
        viewer = user.key.split("/")[-1] if user else ""
        return render_template("design/activity_feed", list(self.VARIANTS), selected, scope, viewer, self._api_url(i.api))

    @classmethod
    def _api_url(cls, requested: str | None) -> str:
        """Resolve the feed endpoint the gallery should fetch from.

        In production nginx routes /api/internal to the FastAPI process, but a
        local dev stack has no proxy between the two servers -- so the origin is
        overridable, e.g. ?api=http://localhost:18080/api/internal/activity/feed.json

        Only a same-host origin is accepted. That covers localhost, 127.0.0.1,
        and the machine's LAN address (so the gallery can be opened from a phone
        or another desk) without letting the parameter point the page's fetch at
        an arbitrary server.
        """
        if not requested:
            return cls.DEFAULT_API
        # `//host/path` is protocol-relative, not a path -- it points at another
        # origin despite starting with a slash.
        if requested.startswith("/") and not requested.startswith("//"):
            return requested

        parsed = urlparse(requested)
        if parsed.scheme not in ("http", "https") or not parsed.path.startswith("/api/"):
            return cls.DEFAULT_API
        if parsed.hostname != urlparse(f"//{web.ctx.host}").hostname:
            return cls.DEFAULT_API
        return requested


def setup():
    pass
