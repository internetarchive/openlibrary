"""Turn what the sources say into one decision per field.

The input is a normalized evidence document: the outside sources' values for
an edition in Open Library's field shape. In phase 1 it comes from a fixture;
later it comes from live lookups. The output is what the wizard renders: the
Open Library value, each source's value and whether it agrees, a verdict, a
suggested value when sources agree, and a meter level with one plain sentence.
"""

from dataclasses import dataclass
from dataclasses import field as dc_field

from openlibrary.first_edits.compare import values_agree
from openlibrary.first_edits.scope import LEVELS
from openlibrary.first_edits.sources import get_sources
from openlibrary.i18n import gettext as _

VERDICTS = ("missing", "differs", "agrees", "conflict", "unverifiable")
# An "agrees" verdict has no mode: confirming a value the catalogs already agree on is left for later.
VERDICT_TO_MODE = {"missing": "fill", "differs": "check"}


@dataclass(frozen=True)
class SourceValue:
    source: str
    raw: object
    display: str
    match: str
    url: str | None
    agrees_with_ol: bool | None


@dataclass(frozen=True)
class FieldEvidence:
    field: str
    ol_raw: object
    ol_display: str
    values: list[SourceValue]
    verdict: str
    level: str
    sentence: str
    suggestion_raw: object = None
    suggestion_display: str = ""
    suggestion_sources: list[str] = dc_field(default_factory=list)

    @property
    def mode(self) -> str | None:
        return VERDICT_TO_MODE.get(self.verdict)

    @property
    def level_index(self) -> int:
        return LEVELS.index(self.level)


def display_value(fld: str, raw, language_names: dict[str, str] | None = None) -> str:
    if raw in (None, "", []):
        return ""
    if fld == "languages":
        names = language_names or {}
        return ", ".join(names.get(code, code) for code in raw)
    if isinstance(raw, list):
        return ", ".join(str(x) for x in raw)
    return str(raw)


def _ol_field(edition_values: dict, fld: str):
    v = edition_values.get(fld)
    return None if v in (None, "", []) else v


def build_field_evidence(fld: str, ol_values: dict, evidence_doc: dict, language_names: dict[str, str] | None = None) -> FieldEvidence:
    """``ol_values`` is the edition's own fields; ``evidence_doc`` is the sources document."""
    ol_raw = _ol_field(ol_values, fld)
    sources = get_sources()
    present = []
    for src in evidence_doc.get("sources", []):
        raw = src.get("fields", {}).get(fld)
        if raw in (None, "", []):
            continue
        present.append((src, raw))

    values = [
        SourceValue(
            source=src["id"],
            raw=raw,
            display=display_value(fld, raw, language_names),
            match=src.get("match", "isbn13"),
            url=src.get("url"),
            agrees_with_ol=values_agree(fld, ol_raw, raw) if ol_raw is not None else None,
        )
        for src, raw in present
    ]
    ol_display = display_value(fld, ol_raw, language_names)

    if not present:
        return FieldEvidence(fld, ol_raw, ol_display, values, "unverifiable", "none", _("No outside source has this field for this edition."))

    # Do the sources agree with each other? Two sources is the phase 1 ceiling.
    first_raw = present[0][1]
    all_agree = all(values_agree(fld, first_raw, raw) for _src, raw in present[1:])
    exact = all(src.get("match", "isbn13") in ("isbn13", "isbn10", "lccn", "oclc") for src, _raw in present)
    names = [sources[src["id"]].name if src["id"] in sources else src["id"] for src, _raw in present]

    if not all_agree:
        return FieldEvidence(
            fld,
            ol_raw,
            ol_display,
            values,
            "conflict",
            "weak",
            _("Needs judgment: %(sources)s disagree with each other, so this one is for a librarian.", sources=_join(names)),
        )

    if len(present) >= 2:
        level = "strong" if exact else "fair"
        sentence = (
            _("Strong: %(sources)s agree, both found by exact ISBN.", sources=_join(names))
            if exact
            else _("Fair: %(sources)s agree, but one was matched by title and author, which is less certain.", sources=_join(names))
        )
    else:
        level = "fair" if exact else "weak"
        sentence = (
            _("Fair: only %(source)s has this, found by exact ISBN.", source=names[0])
            if exact
            else _("Weak: only %(source)s has this, matched by title and author.", source=names[0])
        )

    # Prefer the library catalog's spelling for the suggestion.
    preferred = min(present, key=lambda p: 0 if sources.get(p[0]["id"]) and sources[p[0]["id"]].kind == "library" else 1)[1]
    if ol_raw is None:
        verdict = "missing"
    elif values_agree(fld, ol_raw, first_raw):
        verdict = "agrees"
    else:
        verdict = "differs"

    return FieldEvidence(
        fld,
        ol_raw,
        ol_display,
        values,
        verdict,
        level,
        sentence,
        suggestion_raw=preferred,
        suggestion_display=display_value(fld, preferred, language_names),
        suggestion_sources=[src["id"] for src, _raw in present],
    )


def _join(names: list[str]) -> str:
    if len(names) <= 1:
        return names[0] if names else ""
    return _("%(first)s and %(last)s", first=", ".join(names[:-1]), last=names[-1])
