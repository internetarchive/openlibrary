import json
import logging
from pathlib import Path

from infogami.utils import delegate
from infogami.utils.view import render_template

logger = logging.getLogger("openlibrary.design")

# Committed Custom Elements Manifest generated from JSDoc on the Lit components
# by `npx cem analyze` (see custom-elements-manifest.config.mjs). Regenerated as
# part of `make lit-components`.
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
    """Index cleaned component API data by tag name from the committed manifest.

    Returns an empty dict if the manifest is missing or unreadable so the design
    page still renders its hand-written live demos.
    """
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except OSError, ValueError:
        logger.warning("Could not read Custom Elements Manifest at %s", MANIFEST_PATH)
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


def setup():
    pass
