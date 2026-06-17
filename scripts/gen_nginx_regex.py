#!/usr/bin/env python3
"""Generate nginx PCRE regex(es) that match every FastAPI endpoint.

Pulls the OpenAPI spec, converts each path template into a regex segment,
and prints two bare PCRE regexes to stdout (no nginx wrapper):

  1. A regex for all ``.json`` endpoints
  2. A regex for all non-``.json`` endpoints

Splitting by suffix lets each regex use tighter collapsing (e.g. the
``.json`` regex can anchor every fragment with ``\\.json``) and keeps
each regex short and readable.

Behavior is fully driven by the hardcoded constants below. Diagnostic
info (counts, warnings, verify result) is printed to stderr so stdout
stays clean.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Iterable

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
# OpenAPI spec location.
DEFAULT_OPENAPI_URL = "http://localhost:18080/openapi.json"

# Paths that should never be matched by the regex. Matched on the FastAPI
# path template (e.g. "/health"), not on a real URL.
EXCLUDE_PATHS: set[str] = {
    "/health",
}

# Drop any path whose template starts with one of these prefixes. Used
# when a whole family of routes is served by the legacy web.py app or
# otherwise shouldn't be proxied to FastAPI.
EXCLUDE_PREFIXES: tuple[str, ...] = (
    "/account",  # account routes are still served by the legacy web.py app
)

# Master switch for collapsing. When False, every path is emitted as its
# own per-path branch (no wildcard fragments from COLLAPSE_PREFIXES are
# applied). Flip to True to use the collapse rules below.
ENABLE_COLLAPSING: bool = False

# Instead of expanding every child path individually, emit a single
# wildcard branch. Each entry maps a path template prefix (matched with
# ``str.startswith``) to an nginx/PCRE regex fragment (no leading slash,
# no anchors). Only used when ``ENABLE_COLLAPSING`` is True. Ordered
# roughly by impact (most paths collapsed first).
COLLAPSE_PREFIXES: dict[str, str] = {
    "/partials/": r"partials/.*\.json",  # 8 paths -> 1
    "/people/": r"people/.*",  # 8 paths -> 1
    "/works/OL": r"works/OL\d+W/.*",  # 6 paths -> 1
    "/search": r"search.*\.json",  # 5 paths -> 1
    "/lists/": r"lists/.*\.json",  # 5 paths -> 1
    "/series/": r"series/.*\.json",  # 4 paths -> 1
    "/api/volumes/": r"api/volumes/.*\.json",  # 2 paths -> 1
    "/subjects/": r"subjects/.*\.json",  # 2 paths -> 1
}

# Suffix used to partition paths into the two location blocks.
JSON_SUFFIX = ".json"

# HTTP methods that count as "this path is real, include it in the regex".
HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}

# Realistic sample values used to materialize a path template for
# verification. Enum-typed placeholders are overridden by their first
# enum value at verify time, so SAMPLE_SUBS only needs to cover
# free-form placeholders.
SAMPLE_SUBS: dict[str, str] = {
    "req": "OL12345M",
    "idval": "9780140449266",
    "author_id": "12345",
    "edition_id": "12345",
    "work_id": "12345",
    "list_id": "OL1L",
    "olid": "OL1L",
    "username": "me",
    "subject_key": "love",
    "filename": "cover.jpg",
    "check_in_id": "42",
}


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
def fetch_openapi(url: str) -> dict:
    """Fetch and parse the OpenAPI JSON document at ``url``."""
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read())


def collect_paths(spec: dict) -> list[str]:
    """Return a sorted, de-duplicated list of path templates from the spec.

    A path is included if it has at least one operation (GET, POST, ...).
    Methods don't change the path, so we emit each path once.
    """
    seen: set[str] = set()
    out: list[str] = []
    for path, methods in spec.get("paths", {}).items():
        if any(m.lower() in HTTP_METHODS for m in methods) and path not in seen:
            seen.add(path)
            out.append(path)
    out.sort()
    return out


def collect_path_enums(spec: dict) -> dict[str, dict[str, list[str]]]:
    """Extract enum constraints for path parameters from the spec.

    Returns a dict mapping each path template to ``{param_name: [values]}``
    for every path parameter that has an ``enum`` constraint on its schema.
    Used by ``path_to_regex`` to emit tight alternations like
    ``(want-to-read|currently-reading|already-read)`` instead of ``[^/]+``.
    """
    out: dict[str, dict[str, list[str]]] = {}
    for path, methods in spec.get("paths", {}).items():
        enums: dict[str, list[str]] = {}
        for op in methods.values():
            for p in op.get("parameters", []):
                if p.get("in") != "path":
                    continue
                schema = p.get("schema") or {}
                values = schema.get("enum")
                if isinstance(values, list) and values and all(isinstance(v, str) for v in values):
                    enums[p["name"]] = values
        if enums:
            out[path] = enums
    return out


def path_to_regex(template: str, enums: dict[str, list[str]] | None = None) -> str:
    """Convert a FastAPI path template into an nginx/PCRE-safe regex segment.

    Example::

        /works/OL{work_id}W/lists.json
            -> /works/OL[^/]+W/lists\\.json

        /people/{username}/books/{key}.json   (with key in {want-to-read, ...})
            -> /people/[^/]+/books/(want-to-read|currently-reading|...)\\.json

    Rules:
      * Literal characters are escaped so dots, pluses, etc. don't become
        regex metacharacters.
      * Each ``{name}`` placeholder becomes ``[^/]+`` (any non-slash chars)
        unless ``enums`` provides an enum for that name, in which case a
        tight alternation ``(v1|v2|...)`` is emitted instead.
    """
    out: list[str] = []
    for m in re.finditer(r"\{[^}]+\}|.", template, flags=re.DOTALL):
        token = m.group(0)
        if token.startswith("{"):
            name = token[1:-1]
            if enums and name in enums:
                values = enums[name]
                out.append("(" + "|".join(re.escape(v) for v in values) + ")")
            else:
                out.append(r"[^/]+")
        else:
            out.append(re.escape(token))
    return "".join(out)


def _apply_collapses(templates: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    """Split ``templates`` into (per-path, collapses) using COLLAPSE_PREFIXES.

    A path whose template starts with a collapse prefix is grouped under
    the corresponding fragment; the rest stay as per-path branches.

    When ``ENABLE_COLLAPSING`` is False, no collapsing is performed and
    every template is returned as a per-path branch.
    """
    if not ENABLE_COLLAPSING:
        return list(templates), {}
    collapse_map: dict[str, list[str]] = {}
    remaining: list[str] = []
    for tpl in templates:
        collapsed_into: str | None = None
        for prefix, fragment in COLLAPSE_PREFIXES.items():
            if tpl.startswith(prefix):
                collapsed_into = fragment
                break
        if collapsed_into is not None:
            collapse_map.setdefault(collapsed_into, []).append(tpl)
        else:
            remaining.append(tpl)
    return remaining, collapse_map


def _assemble_regex(
    per_path: list[str],
    collapses: dict[str, list[str]],
    enum_map: dict[str, dict[str, list[str]]] | None = None,
    suffix: str | None = None,
) -> str:
    """Combine per-path branches and collapse branches into a single regex.

    If ``suffix`` is provided (e.g. ``".json"``), strip it from the end
    of every branch and append it once outside the alternation group, so
    the final pattern is ``^/(branches...)\\.json$`` instead of repeating
    ``\\.json`` inside every branch. Branches that don't end with
    ``suffix`` are left untouched (they shouldn't appear in a block that
    uses ``suffix``, but we don't crash if they do).
    """
    enum_map = enum_map or {}
    # Strip the leading "/" from per-path branches so the outer "^/" in
    # the anchor doesn't double up.
    branches = [path_to_regex(t.removeprefix("/"), enum_map.get(t)) for t in per_path]
    collapse_branches = [frag for frag in COLLAPSE_PREFIXES.values() if frag in collapses]
    all_branches = collapse_branches + branches
    if not all_branches:
        return ""
    if suffix:
        esc = re.escape(suffix)
        all_branches = [b.removesuffix(esc) for b in all_branches]
        return r"^/(" + "|".join(all_branches) + ")" + esc + r"$"
    return r"^/(" + "|".join(all_branches) + r")$"


def build_combined_regex(
    templates: Iterable[str],
    enum_map: dict[str, dict[str, list[str]]] | None = None,
) -> tuple[str, dict[str, list[str]]]:
    """Build the single combined regex (used internally + by verify)."""
    enum_map = enum_map or {}
    filtered = [t for t in templates if not any(t.startswith(p) for p in EXCLUDE_PREFIXES)]
    per_path, collapse_map = _apply_collapses(filtered)
    return _assemble_regex(per_path, collapse_map, enum_map), collapse_map


def partition_by_suffix(
    paths: list[str],
    collapse_map: dict[str, list[str]],
    suffix: str = JSON_SUFFIX,
) -> tuple[list[str], list[str], dict[str, list[str]], dict[str, list[str]]]:
    """Split paths and collapse_map by whether templates end with ``suffix``.

    A collapse entry is kept whole only if ALL its replaced paths agree on
    the suffix. Mixed collapses are broken into per-path templates in the
    appropriate partition.

    Returns ``(json_per_path, nonjson_per_path, json_collapses, nonjson_collapses)``.
    """
    collapsed_templates = {t for v in collapse_map.values() for t in v}

    json_per_path: list[str] = []
    nonjson_per_path: list[str] = []
    for tpl in paths:
        if tpl in collapsed_templates:
            continue
        if tpl.endswith(suffix):
            json_per_path.append(tpl)
        else:
            nonjson_per_path.append(tpl)

    json_collapses: dict[str, list[str]] = {}
    nonjson_collapses: dict[str, list[str]] = {}
    for frag, replaced in collapse_map.items():
        all_json = all(t.endswith(suffix) for t in replaced)
        all_nonjson = all(not t.endswith(suffix) for t in replaced)
        if all_json:
            json_collapses[frag] = replaced
        elif all_nonjson:
            nonjson_collapses[frag] = replaced
        else:
            # Mixed collapse: break into per-path branches in the right partition.
            for tpl in replaced:
                if tpl.endswith(suffix):
                    json_per_path.append(tpl)
                else:
                    nonjson_per_path.append(tpl)

    return json_per_path, nonjson_per_path, json_collapses, nonjson_collapses


def build_two_regexes(
    paths: list[str],
    enum_map: dict[str, dict[str, list[str]]] | None = None,
    suffix: str = JSON_SUFFIX,
) -> dict:
    """Build two regexes: one for ``suffix`` paths, one for the rest.

    Returns a dict with keys ``json_pattern``, ``json_per_path``,
    ``json_collapses``, ``nonjson_pattern``, ``nonjson_per_path``,
    ``nonjson_collapses``.
    """
    enum_map = enum_map or {}
    _, collapse_map = build_combined_regex(paths, enum_map)
    json_per, nonjson_per, json_coll, nonjson_coll = partition_by_suffix(paths, collapse_map, suffix)
    return {
        "json_pattern": _assemble_regex(json_per, json_coll, enum_map, suffix=suffix),
        "json_per_path": json_per,
        "json_collapses": json_coll,
        "nonjson_pattern": _assemble_regex(nonjson_per, nonjson_coll, enum_map),
        "nonjson_per_path": nonjson_per,
        "nonjson_collapses": nonjson_coll,
    }


def materialize(template: str, enums: dict[str, list[str]] | None = None) -> str:
    """Substitute realistic sample values into a path template for testing.

    If ``enums`` is provided and contains the placeholder name, the first
    enum value is used (so the materialized URL is guaranteed to match the
    tight alternation emitted by ``path_to_regex``).
    """

    def repl(m: re.Match) -> str:
        name = m.group(0)[1:-1]
        if enums and name in enums:
            return enums[name][0]
        return SAMPLE_SUBS.get(name, "x")

    return re.sub(r"\{[^}]+\}", repl, template)


def _extract_inner(pattern: str) -> str:
    """Extract the alternation content from a ``^/(...)$`` or ``^/(...)\\.json$`` pattern."""
    if pattern.startswith("^/(") and pattern.endswith(")$"):
        return pattern[3:-2]
    if pattern.startswith("^/(") and pattern.endswith(")\\.json$"):
        return pattern[3:-8]  # strip )\.json$ (8 chars: ) \ . j s o n $)
    return ""


def render_combined(
    json_pattern: str,
    nonjson_pattern: str,
) -> str:
    """Render one combined regex combining .json and non-.json branches.

    Falls back to a single-group regex if one of the two partitions
    is empty.
    """
    json_inner = _extract_inner(json_pattern)
    nonjson_inner = _extract_inner(nonjson_pattern)

    if json_inner and nonjson_inner:
        esc = re.escape(JSON_SUFFIX)
        # Strip suffix from each JSON branch (since \.json is now outside the group).
        json_branches = [b.removesuffix(esc) for b in json_inner.split("|")]
        json_combined = "|".join(json_branches)
        return f"^/(?:{json_combined}){esc}|(?:{nonjson_inner})$"
    if json_inner:
        return json_pattern
    if nonjson_inner:
        return nonjson_pattern
    return ""


def render_path_table(
    paths: list[str],
    enum_map: dict[str, dict[str, list[str]]],
    json_per: list[str],
    json_coll: dict[str, list[str]],
    nonjson_per: list[str],
    nonjson_coll: dict[str, list[str]],
    suffix: str = JSON_SUFFIX,
) -> str:
    """Render a markdown-ish table of (block, raw path, regex) for every path.

    For per-path branches, the suffix (e.g. ``\\.json``) is stripped from
    the displayed regex to match how the final pattern hoists it outside
    the alternation group. Collapsed paths show the collapse fragment and
    a ``(collapse)`` marker.
    """
    esc_suffix = re.escape(suffix)
    # Invert collapse maps for fast lookup: path -> (block, fragment)
    collapse_lookup: dict[str, tuple[str, str]] = {}
    for frag, replaced in json_coll.items():
        for tpl in replaced:
            collapse_lookup[tpl] = (".json", frag)
    for frag, replaced in nonjson_coll.items():
        for tpl in replaced:
            collapse_lookup[tpl] = ("non-.json", frag)

    def strip_suffix(s: str) -> str:
        return s.removesuffix(esc_suffix)

    rows: list[tuple[str, str, str]] = []
    json_set = set(json_per)
    nonjson_set = set(nonjson_per)
    for tpl in paths:
        if tpl in json_set:
            regex = path_to_regex(tpl.removeprefix("/"), enum_map.get(tpl))
            rows.append((".json", tpl, strip_suffix(regex)))
        elif tpl in nonjson_set:
            regex = path_to_regex(tpl.removeprefix("/"), enum_map.get(tpl))
            rows.append(("non-.json", tpl, regex))
        elif tpl in collapse_lookup:
            block, frag = collapse_lookup[tpl]
            display = strip_suffix(frag) if block == ".json" else frag
            rows.append((block, tpl, f"{display}  (collapse)"))

    rows.sort(key=lambda r: (r[0], r[1]))

    headers = ("Block", "FastAPI path", "Regex")
    widths = [
        max(len(headers[0]), max((len(r[0]) for r in rows), default=0)),
        max(len(headers[1]), max((len(r[1]) for r in rows), default=0)),
        max(len(headers[2]), max((len(r[2]) for r in rows), default=0)),
    ]

    def fmt(cells: tuple[str, str, str]) -> str:
        return f"  {cells[0]:<{widths[0]}}  {cells[1]:<{widths[1]}}  {cells[2]}"

    lines = [fmt(headers), f"  {'-' * widths[0]}  {'-' * widths[1]}  {'-' * widths[2]}"]
    lines.extend(fmt(r) for r in rows)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> int:
    try:
        spec = fetch_openapi(DEFAULT_OPENAPI_URL)
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        print(
            f"error: failed to fetch OpenAPI spec from {DEFAULT_OPENAPI_URL}: {exc}",
            file=sys.stderr,
        )
        return 2

    all_paths = collect_paths(spec)
    enum_map = collect_path_enums(spec)

    excluded_present = [p for p in all_paths if p in EXCLUDE_PATHS]
    excluded_missing = sorted(EXCLUDE_PATHS - set(all_paths))
    # `paths` mirrors the filtering inside `build_combined_regex` so verify agrees.
    paths = [p for p in all_paths if p not in EXCLUDE_PATHS and not any(p.startswith(pre) for pre in EXCLUDE_PREFIXES)]

    result = build_two_regexes(paths, enum_map)
    json_pattern = result["json_pattern"]
    nonjson_pattern = result["nonjson_pattern"]
    json_per = result["json_per_path"]
    json_coll = result["json_collapses"]
    nonjson_per = result["nonjson_per_path"]
    nonjson_coll = result["nonjson_collapses"]

    # Emit the combined regex to stdout (the useful output).
    print(render_combined(json_pattern, nonjson_pattern))

    # Side-channel diagnostics on stderr.
    json_branch_count = json_pattern.count("|") + 1 if json_pattern else 0
    nonjson_branch_count = nonjson_pattern.count("|") + 1 if nonjson_pattern else 0
    json_collapsed_count = sum(len(v) for v in json_coll.values())
    nonjson_collapsed_count = sum(len(v) for v in nonjson_coll.values())
    prefix_excluded = sum(1 for p in all_paths if p not in EXCLUDE_PATHS and any(p.startswith(pre) for pre in EXCLUDE_PREFIXES))
    print(
        f"# Included {len(paths)} path(s); excluded {len(excluded_present)} by exact match, {prefix_excluded} by prefix.",
        file=sys.stderr,
    )
    print(
        f"# .json block:     {json_branch_count:3d} branches, {len(json_coll)} collapse(s) covering {json_collapsed_count} path(s), {len(json_per)} per-path.",
        file=sys.stderr,
    )
    print(
        f"# non-.json block: {nonjson_branch_count:3d} branches, {len(nonjson_coll)} collapse(s) "
        f"covering {nonjson_collapsed_count} path(s), {len(nonjson_per)} per-path.",
        file=sys.stderr,
    )
    for frag, replaced in {**json_coll, **nonjson_coll}.items():
        print(f"# Collapse {frag!r} replaces {len(replaced)} path(s).", file=sys.stderr)
    if excluded_missing:
        print(
            f"# Warning: {len(excluded_missing)} exclusion(s) not found in spec: {', '.join(excluded_missing)}",
            file=sys.stderr,
        )

    # Path-to-regex mapping table (stderr, for easy verification).
    print(
        render_path_table(paths, enum_map, json_per, json_coll, nonjson_per, nonjson_coll),
        file=sys.stderr,
    )

    # Always verify both patterns.
    misses: list[str] = []

    def verify_partition(per_path, collapses, pattern, label):
        if not pattern:
            return
        rx = re.compile(pattern)
        collapsed_templates = {t for v in collapses.values() for t in v}
        for tpl in per_path:
            if tpl in collapsed_templates:
                continue
            url = materialize(tpl, enum_map.get(tpl))
            if not rx.match(url):
                misses.append(f"[{label}] {tpl}  ->  {url}")
        for frag, replaced in collapses.items():
            branch_rx = re.compile(r"^/(" + frag + r")$")
            for tpl in replaced:
                url = materialize(tpl, enum_map.get(tpl))
                if not branch_rx.match(url):
                    misses.append(f"[{label}] COLLAPSE {frag!r} failed on {tpl}  ->  {url}")

    verify_partition(json_per, json_coll, json_pattern, ".json")
    verify_partition(nonjson_per, nonjson_coll, nonjson_pattern, "non-.json")

    if misses:
        print(f"# VERIFY FAILED for {len(misses)} path(s):", file=sys.stderr)
        for m in misses:
            print(f"#   {m}", file=sys.stderr)
        return 1

    print(
        f"# Verified: both regexes match all {len(paths)} included path(s).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
