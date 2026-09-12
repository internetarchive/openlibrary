"""Facts about a record, at the moment an editor is deciding what to do with it.

Three consumers:

* the ambient **health strip** on work, edition and author pages in editing
  mode (``health``): provenance, author mismatch, impact, scan, pending
  requests, strong identifiers, cheap smells;
* the **preview checks** the batch endpoint runs per action (``checks_for``):
  block / warn / info with evidence links;
* redirect-safe **record loading** shared by everything librarian-facing
  (``resolve_key``, ``load_docs``).

Everything here reads; nothing writes. The health strip reads local data only;
the preview checks may consult Wikidata (cached) and say so when they cannot.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any, Literal

from openlibrary.core import cache
from openlibrary.core.bookshelves import Bookshelves
from openlibrary.core.edits import CommunityEditsQueue
from openlibrary.core.librarian_batches import LibrarianBatches
from openlibrary.core.wikidata import WikidataEntity, get_wikidata_entity
from openlibrary.utils.request_context import site

logger = logging.getLogger("openlibrary.record_context")

Level = Literal["block", "warn", "info", "ok"]
RecordType = Literal["work", "edition", "author"]

OLID_RE = re.compile(r"^OL\d+[AWM]$")
KEY_RE = re.compile(r"^/(works|books|authors)/OL\d+[WMA]$")
PREFIX_BY_SUFFIX = {"W": "/works", "M": "/books", "A": "/authors"}
TYPE_BY_PREFIX: dict[str, RecordType] = {"/works": "work", "/books": "edition", "/authors": "author"}
TYPE_BY_TYPEKEY: dict[str, RecordType] = {"/type/work": "work", "/type/edition": "edition", "/type/author": "author"}

# Author-name fragments that mean an import folded a role into the name (#7797, #7756).
ROLE_WORDS = re.compile(
    r"\b(illustrator|illustrated by|editor|edited by|translator|translated by|introduction by|foreword by|narrator|compiler|et al\.?)\b",
    re.IGNORECASE,
)
BOT_AUTHOR = re.compile(r"bot$", re.IGNORECASE)

# Import sources that create most of the junk librarians clean up (#6555, #3432).
LOW_TRUST_SOURCES = {"bwb", "amazon", "idb", "osp", "promise"}
SOURCE_NAMES = {
    "ia": "Internet Archive",
    "marc": "MARC record",
    "bwb": "Better World Books",
    "amazon": "Amazon",
    "google_books": "Google Books",
    "idb": "ISBNdb",
    "osp": "ISBNdb",
    "promise": "Promise item",
    "openalex": "OpenAlex",
    "wikisource": "Wikisource",
    "standard_ebooks": "Standard Ebooks",
}

WD_BIRTH, WD_DEATH, WD_VIAF, WD_ISNI, WD_LC = "P569", "P570", "P214", "P213", "P244"


# ── Keys and documents ────────────────────────────────────────────────


def normalize_key(value: str) -> str | None:
    """'OL1W', '/works/OL1W' or a full URL → '/works/OL1W'. None if not a record key."""
    if not value:
        return None
    v = value.strip()
    if m := re.search(r"/(works|books|authors)/(OL\d+[WMA])", v):
        return f"/{m.group(1)}/{m.group(2)}"
    if OLID_RE.match(v):
        return f"{PREFIX_BY_SUFFIX[v[-1]]}/{v}"
    return None


def key_type(key: str) -> RecordType | None:
    return TYPE_BY_PREFIX.get(key.rsplit("/", 1)[0]) if key else None


def olid(key: str) -> str:
    return key.rsplit("/", 1)[-1]


def doc_type(doc: dict[str, Any] | None) -> str | None:
    if not doc:
        return None
    t = doc.get("type")
    return t.get("key") if isinstance(t, dict) else t


def resolve_key(key: str, max_hops: int = 5) -> tuple[str, dict[str, Any] | None, list[str]]:
    """Follow redirects. Returns (resolved key, raw doc or None, chain of keys followed)."""
    chain: list[str] = []
    current = key
    for _ in range(max_hops):
        thing = site.get().get(current)
        if thing is None:
            return current, None, chain
        doc = thing.dict()
        if doc_type(doc) == "/type/redirect" and doc.get("location"):
            chain.append(current)
            current = doc["location"]
            continue
        return current, doc, chain
    return current, None, chain


def load_docs(keys: list[str]) -> tuple[dict[str, dict[str, Any]], dict[str, str], list[str]]:
    """Load many records, following redirects.

    Returns (docs by resolved key, {requested key: resolved key} for the ones that
    moved, missing keys).
    """
    docs: dict[str, dict[str, Any]] = {}
    resolved: dict[str, str] = {}
    missing: list[str] = []
    things = site.get().get_many(list(dict.fromkeys(keys)))
    by_key = {t.key: t.dict() for t in things}
    for key in keys:
        doc = by_key.get(key)
        if doc is None:
            missing.append(key)
            continue
        if doc_type(doc) == "/type/redirect":
            final, final_doc, _chain = resolve_key(key)
            if final_doc is None:
                missing.append(key)
                continue
            resolved[key] = final
            docs[final] = final_doc
        else:
            docs[key] = doc
    return docs, resolved, missing


def ref_keys(refs: Any) -> list[str]:
    """Author refs come as [{'author': {'key': ...}}] on works, [{'key': ...}] on editions."""
    out = []
    for r in refs or []:
        if isinstance(r, dict):
            inner = r.get("author", r)
            if isinstance(inner, dict) and inner.get("key"):
                out.append(inner["key"])
        elif isinstance(r, str):
            out.append(r)
    return out


def resolved_ref_keys(refs: Any) -> list[str]:
    """Author refs with redirects followed, so merged authors compare equal."""
    keys = ref_keys(refs)
    if not keys:
        return []
    _docs, resolved, _missing = load_docs(keys)
    return [resolved.get(k, k) for k in keys]


# ── Small shared helpers ─────────────────────────────────────────────


def chip(code: str, level: Level, text: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "level": level, "text": text, **extra}


def norm_title(s: str | None) -> str:
    s = (s or "").lower()
    s = re.sub(r"^(the|a|an)\s+", "", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def year_of(s: str | None) -> int | None:
    if m := re.search(r"(\d{4})", s or ""):
        return int(m.group(1))
    return None


def parse_source(record_id: str) -> tuple[str, str]:
    """'bwb:9780...' → ('bwb', 'Better World Books'); 'marc:marc_loc/...' → ('marc', 'MARC record')."""
    rid = record_id
    if rid.startswith("marc:"):
        return "marc", SOURCE_NAMES["marc"]
    prefix = rid.split(":", 1)[0] if ":" in rid else "catalog"
    return prefix, SOURCE_NAMES.get(prefix, prefix if prefix != "catalog" else "a library catalog")


def _wd_year(entity: WikidataEntity | None, prop: str) -> int | None:
    if not entity:
        return None
    for st in entity.statements.get(prop, []):
        content = (st.get("value") or {}).get("content")
        if isinstance(content, dict) and (t := content.get("time")):
            return year_of(t)
        if isinstance(content, str):
            return year_of(content)
    return None


def _wd_ids(entity: WikidataEntity | None, prop: str) -> list[str]:
    if not entity:
        return []
    return entity._get_statement_values(prop)


def wikidata_for(doc: dict[str, Any]) -> WikidataEntity | None:
    qid = (doc.get("remote_ids") or {}).get("wikidata")
    if not qid:
        return None
    try:
        return get_wikidata_entity(qid, fetch_missing=True)
    except Exception:
        logger.warning("wikidata lookup failed for %s", qid, exc_info=True)
        return None


def _changes_for(key: str, limit: int = 40) -> list[Any]:
    try:
        return site.get().recentchanges({"key": key, "limit": limit})
    except Exception:
        logger.warning("recentchanges failed for %s", key, exc_info=True)
        return []


def _solr_doc(key: str, fields: list[str]) -> dict[str, Any]:
    try:
        from openlibrary.plugins.worksearch.search import get_solr

        return get_solr().get(key, fields=fields) or {}
    except Exception:
        logger.warning("solr get failed for %s", key, exc_info=True)
        return {}


def _lists_count(key: str) -> int:
    try:
        thing = site.get().get(key)
        return len(thing.get_lists(limit=200)) if thing else 0
    except Exception:  # noqa: BLE001
        return 0


def _readinglog_count(work_key: str) -> int:
    try:
        summary = Bookshelves.get_work_summary(olid(work_key)[2:-1])
        return sum(v for v in summary.values() if isinstance(v, int))
    except Exception:  # noqa: BLE001
        return 0


def pending_for(key: str) -> list[dict[str, Any]]:
    """Open merge requests and requested batches that touch this record."""
    out: list[dict[str, Any]] = []
    try:
        from openlibrary.core import db

        rows = db.get_db().query(
            "SELECT id, mr_type, title, submitter FROM community_edits_queue WHERE status=$status AND url LIKE $pattern",
            vars={"status": CommunityEditsQueue.STATUS["PENDING"], "pattern": f"%{olid(key)}%"},
        )
        out.extend({"kind": "merge_request", "id": r["id"], "title": r["title"], "url": f"/merges?mrid={r['id']}"} for r in rows)
    except Exception:
        logger.warning("pending merge lookup failed for %s", key, exc_info=True)
    try:
        out.extend({"kind": "batch", "id": b["id"], "title": b["action"], "url": f"/librarians/batch/{b['id']}"} for b in LibrarianBatches.pending_for_key(key))
    except Exception:
        logger.warning("pending batch lookup failed for %s", key, exc_info=True)
    return out


# ── Health strip ─────────────────────────────────────────────────────


def _provenance(doc: dict[str, Any], key: str) -> dict[str, Any] | None:
    sources = doc.get("source_records") or []
    changes = _changes_for(key)
    human = [c for c in changes if c.author and not BOT_AUTHOR.search(olid(c.author.key))]
    created = doc.get("created")
    created_year = year_of(created.get("value") if isinstance(created, dict) else str(created or ""))
    prefixes = {parse_source(s)[0] for s in sources}
    names = sorted({parse_source(s)[1] for s in sources})
    low_trust = bool(prefixes) and prefixes <= LOW_TRUST_SOURCES
    if names:
        text = f"Imported from {', '.join(names)}" + (f", {created_year}" if created_year else "")
    elif created_year:
        text = f"Created {created_year}"
    else:
        text = "Provenance unknown"
    if changes:
        text += f" · {len(human)} human edit{'s' if len(human) != 1 else ''}" if human else " · no human edits"
    level: Level = "warn" if (low_trust and not human) else "info"
    return chip(
        "provenance",
        level,
        text,
        detail={"sources": sources[:10], "human_edits": len(human), "total_edits": len(changes)},
        href=f"{key}?m=history",
    )


def _author_mismatch(edition: dict[str, Any], work: dict[str, Any] | None) -> dict[str, Any] | None:
    if not work:
        return None
    e_auth = set(resolved_ref_keys(edition.get("authors")))
    w_auth = set(resolved_ref_keys(work.get("authors")))
    if e_auth and w_auth and e_auth.isdisjoint(w_auth):
        return chip(
            "author_mismatch",
            "block",
            "Edition author ≠ work author",
            detail={"edition_authors": sorted(e_auth), "work_authors": sorted(w_auth)},
            href=f"{edition['key']}.json",
        )
    return None


def _smells(doc: dict[str, Any], rtype: RecordType) -> list[dict[str, Any]]:
    out = []
    if rtype == "author" and ROLE_WORDS.search(doc.get("name") or ""):
        out.append(chip("role_in_name", "warn", "Name contains a role word (editor, illustrator…)"))
    if rtype == "edition":
        y = year_of(doc.get("publish_date"))
        if y and y > datetime.now(UTC).year + 1:
            out.append(chip("future_date", "warn", f"Publish date {y} is in the future"))
        if not doc.get("works"):
            out.append(chip("orphan_edition", "warn", "Edition has no work"))
        if doc.get("covers") and all(c == -1 for c in doc["covers"]):
            out.append(chip("placeholder_cover", "info", "Placeholder cover"))
        if not (doc.get("isbn_10") or doc.get("isbn_13") or doc.get("ocaid") or doc.get("lccn") or doc.get("oclc_numbers")):
            out.append(chip("no_identifiers", "info", "No ISBN, LCCN, OCLC or scan"))
    if rtype == "work" and not doc.get("authors"):
        out.append(chip("no_authors", "warn", "Work has no authors"))
    return out


def _scan(edition: dict[str, Any]) -> dict[str, Any] | None:
    """The strip is ambient (every record page a librarian views), so it says a scan is
    linked without asking archive.org whether it exists; the merge checks do that on demand."""
    ocaid = edition.get("ocaid")
    if not ocaid:
        return None
    return chip("scan", "info", f"Scanned: {ocaid}", href=f"https://archive.org/details/{ocaid}")


def _strong_ids(author: dict[str, Any]) -> list[dict[str, Any]]:
    ids = author.get("remote_ids") or {}
    strong = [k for k in ("wikidata", "viaf", "lc_naf", "isni") if ids.get(k)]
    if strong:
        href = f"https://www.wikidata.org/wiki/{ids['wikidata']}" if ids.get("wikidata") else None
        return [chip("strong_ids", "ok", "IDs: " + ", ".join(strong), detail={k: ids[k] for k in strong}, **({"href": href} if href else {}))]
    return [chip("no_strong_ids", "info", "No Wikidata, VIAF, LC or ISNI id")]


def health(key: str) -> dict[str, Any]:
    """The ambient strip for one record. Local reads only (records, edit history, Solr, lists,
    reading logs, the queue); external lookups belong to the on-demand preview checks."""
    rkey, doc, chain = resolve_key(key)
    if not doc:
        return {"key": key, "type": None, "chips": [chip("missing", "block", "Record not found")], "impact": {}}
    rtype = TYPE_BY_TYPEKEY.get(doc_type(doc) or "")
    if rtype is None:
        return {"key": rkey, "type": None, "chips": [chip("type", "info", f"Type {doc_type(doc)}")], "impact": {}}
    chips: list[dict[str, Any]] = []
    impact: dict[str, Any] = {}
    if chain:
        chips.append(chip("redirect", "info", f"Redirected from {olid(chain[0])}"))
    if p := _provenance(doc, rkey):
        chips.append(p)

    if rtype == "edition":
        work_key = next(iter(ref_keys(doc.get("works"))), None)
        work = None
        if work_key:
            _wk, work, _c = resolve_key(work_key)
        if m := _author_mismatch(doc, work):
            chips.append(m)
        if work:
            impact["editions"] = _solr_doc(work["key"], ["edition_count"]).get("edition_count")
            impact["lists"] = _lists_count(work["key"]) + _lists_count(rkey)
            impact["readinglog"] = _readinglog_count(work["key"])
        if s := _scan(doc):
            chips.append(s)
    elif rtype == "work":
        sd = _solr_doc(rkey, ["edition_count"])
        impact["editions"] = sd.get("edition_count")
        impact["lists"] = _lists_count(rkey)
        impact["readinglog"] = _readinglog_count(rkey)
        if sd.get("edition_count") == 0:
            chips.append(chip("no_editions", "warn", "Work has no editions"))
    elif rtype == "author":
        sd = _solr_doc(rkey, ["work_count"])
        impact["works"] = sd.get("work_count")
        impact["lists"] = _lists_count(rkey)
        chips.extend(_strong_ids(doc))

    parts = []
    if impact.get("editions") is not None:
        parts.append(f"{impact['editions']} edition{'s' if impact['editions'] != 1 else ''}")
    if impact.get("works") is not None:
        parts.append(f"{impact['works']} work{'s' if impact['works'] != 1 else ''}")
    if impact.get("lists"):
        parts.append(f"on {impact['lists']} list{'s' if impact['lists'] != 1 else ''}")
    if impact.get("readinglog"):
        parts.append(f"{impact['readinglog']} reading log{'s' if impact['readinglog'] != 1 else ''}")
    if parts:
        chips.append(chip("impact", "info", " · ".join(parts), detail=impact))

    chips.extend(_smells(doc, rtype))

    if pending := pending_for(rkey):
        n = len(pending)
        chips.append(chip("pending", "warn", f"{n} open request{'s' if n != 1 else ''} on this record", detail=pending, href=pending[0]["url"]))

    return {"key": rkey, "type": rtype, "title": doc.get("title") or doc.get("name"), "revision": doc.get("revision"), "chips": chips, "impact": impact}


# ── Preview checks ───────────────────────────────────────────────────


def _w(level: Level, code: str, text: str, key: str | None = None, evidence: list[str] | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {"level": level, "code": code, "text": text}
    if key:
        d["key"] = key
    if evidence:
        d["evidence"] = evidence
    return d


def _is_not_link(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """The admin-only 'is not' relation (#9500) stored under a few historical names."""
    for field in ("is_not", "not_same_as", "not_merge_with"):
        for src, other in ((a, b), (b, a)):
            if other["key"] in ref_keys(src.get(field)) or other["key"] in (src.get(field) or []):
                return True
    return False


def check_merge_authors(docs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    items = list(docs.values())
    if len(items) < 2:
        return out
    entities = {d["key"]: wikidata_for(d) for d in items}
    qids = {d["key"]: (d.get("remote_ids") or {}).get("wikidata") for d in items}
    distinct_q = {q for q in qids.values() if q}
    if len(distinct_q) > 1:
        out.append(
            _w(
                "block",
                "different_wikidata",
                "The records point at different Wikidata items. Merging would join two people.",
                evidence=[f"https://www.wikidata.org/wiki/{q}" for q in sorted(distinct_q)],
            )
        )
    for field, label in (("viaf", "VIAF"), ("lc_naf", "Library of Congress"), ("isni", "ISNI")):
        ids = {str(v) for d in items if (v := (d.get("remote_ids") or {}).get(field))}
        if len(ids) > 1:
            out.append(_w("warn", f"different_{field}", f"{label} ids differ across the records ({', '.join(sorted(ids))})."))
    births = {d["key"]: year_of(d.get("birth_date")) or _wd_year(entities[d["key"]], WD_BIRTH) for d in items}
    deaths = {d["key"]: year_of(d.get("death_date")) or _wd_year(entities[d["key"]], WD_DEATH) for d in items}
    for label, years in (("Birth", births), ("Death", deaths)):
        vals: set[int] = {y for y in years.values() if y is not None}
        if len(vals) > 1 and (max(vals) - min(vals)) > 2:
            out.append(_w("warn", f"{label.lower()}_years_differ", f"{label} years differ: " + ", ".join(f"{olid(k)} {y}" for k, y in years.items() if y)))
    for a in items:
        for b in items:
            if a["key"] < b["key"] and _is_not_link(a, b):
                out.append(_w("block", "is_not", f"{olid(a['key'])} is marked as not the same as {olid(b['key'])}.", evidence=[a["key"], b["key"]]))
    names = {norm_title(d.get("name")) for d in items}
    if len(names) > 1:
        out.append(_w("info", "names_differ", "Names differ: " + " / ".join(d.get("name") or "?" for d in items)))
    counts = {d["key"]: _solr_doc(d["key"], ["work_count", "top_work"]) for d in items}
    for k, sd in counts.items():
        if sd.get("work_count", 0) > 500:
            out.append(_w("info", "large_author", f"{olid(k)} has {sd['work_count']} works; the merge will take a while to show in search.", key=k))
    oldest = min(items, key=lambda d: int(olid(d["key"])[2:-1]))
    out.append(_w("info", "primary", f"Surviving record will be {olid(oldest['key'])} (oldest id).", key=oldest["key"]))
    return out


def check_merge_works(docs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    items = list(docs.values())
    if len(items) < 2:
        return out
    author_sets = {d["key"]: set(resolved_ref_keys(d.get("authors"))) for d in items}
    non_empty = [s for s in author_sets.values() if s]
    if len(non_empty) > 1 and not set.intersection(*non_empty):
        out.append(_w("warn", "different_authors", "The works have no author in common.", evidence=[d["key"] for d in items]))
    for a in items:
        for b in items:
            if a["key"] < b["key"] and _is_not_link(a, b):
                out.append(_w("block", "is_not", f"{olid(a['key'])} is marked as not the same as {olid(b['key'])}."))
    solr = {d["key"]: _solr_doc(d["key"], ["first_publish_year", "language", "edition_count"]) for d in items}
    years = {y for sd in solr.values() if (y := sd.get("first_publish_year"))}
    if len(years) > 1 and max(years) - min(years) > 40:
        out.append(_w("warn", "years_far_apart", f"First publication years span {min(years)}-{max(years)}; check these are the same work."))
    langs = {tuple(sorted(sd.get("language") or [])) for sd in solr.values()}
    langs.discard(())
    if len(langs) > 1 and not set.intersection(*(set(lang) for lang in langs)):
        out.append(
            _w(
                "info",
                "different_languages",
                "Editions are in different languages; that is fine for one work, but check it is a translation and not a different book.",
            )
        )
    titles = {norm_title(d.get("title")) for d in items}
    if len(titles) > 1:
        out.append(_w("info", "titles_differ", "Titles differ: " + " / ".join(d.get("title") or "?" for d in items)))
    for d in items:
        n = _lists_count(d["key"])
        if n >= 5:
            out.append(_w("warn", "on_lists", f"{olid(d['key'])} is on {n} lists; list entries follow the redirect but some members will notice.", key=d["key"]))
    total = sum(sd.get("edition_count") or 0 for sd in solr.values())
    if total > 1:
        out.append(_w("info", "editions_after", f"The surviving work will have about {total} editions; duplicate editions can be merged afterwards."))
    return out


def check_move_editions(docs: dict[str, dict[str, Any]], target: dict[str, Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if target is None:
        return out
    t_auth = set(resolved_ref_keys(target.get("authors")))
    t_title = norm_title(target.get("title"))
    for d in docs.values():
        if doc_type(d) != "/type/edition":
            continue
        if target["key"] in ref_keys(d.get("works")):
            out.append(_w("info", "already_there", f"{olid(d['key'])} is already on {olid(target['key'])}.", key=d["key"]))
            continue
        e_auth = set(resolved_ref_keys(d.get("authors")))
        if e_auth and t_auth and e_auth.isdisjoint(t_auth):
            out.append(
                _w(
                    "warn",
                    "author_mismatch",
                    f"{olid(d['key'])}'s authors differ from {olid(target['key'])}'s.",
                    key=d["key"],
                    evidence=[d["key"], target["key"]],
                )
            )
        elif not e_auth and d.get("by_statement") and t_auth:
            out.append(_w("info", "by_statement", f"{olid(d['key'])} by-statement: “{d['by_statement']}” — check it matches the target's author.", key=d["key"]))
        et = norm_title(d.get("title"))
        if et and t_title and et[:12] != t_title[:12]:
            out.append(_w("warn", "title_mismatch", f"{olid(d['key'])} “{d.get('title')}” vs work “{target.get('title')}”.", key=d["key"]))
    return out


def check_set_author(docs: dict[str, dict[str, Any]], author: dict[str, Any] | None, include_editions: bool) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if author is None:
        return out
    if doc_type(author) != "/type/author":
        out.append(_w("block", "not_an_author", f"{author['key']} is not an author record."))
    if not include_editions:
        out.append(_w("info", "editions_untouched", "Edition-level authors are left as they are; turn on “include editions” to keep them in step (#13265)."))
    return out


def check_tag(docs: dict[str, dict[str, Any]], adds: dict[str, list[str]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for stype, names in (adds or {}).items():
        for name in names or []:
            n = norm_title(name)
            for d in docs.values():
                for existing in d.get(stype) or []:
                    if existing != name and norm_title(existing) == n:
                        out.append(
                            _w(
                                "warn",
                                "near_duplicate_subject",
                                f"“{name}” is close to existing “{existing}” on {olid(d['key'])}; consider reusing it.",
                                key=d["key"],
                            )
                        )
                        break
    return out


def check_flag_or_delete(docs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for d in docs.values():
        rtype = TYPE_BY_TYPEKEY.get(doc_type(d) or "")
        if rtype == "edition" and d.get("ocaid"):
            out.append(_w("block", "has_scan", f"{olid(d['key'])} has a scan on archive.org; a scanned book is rarely spam.", key=d["key"]))
        if rtype == "work":
            rl = _readinglog_count(d["key"])
            if rl >= 25:
                out.append(_w("block", "in_reading_logs", f"{olid(d['key'])} is in {rl} reading logs.", key=d["key"]))
            elif rl:
                out.append(_w("warn", "in_reading_logs", f"{olid(d['key'])} is in {rl} reading log{'s' if rl != 1 else ''}.", key=d["key"]))
        n = _lists_count(d["key"])
        if n:
            out.append(_w("warn", "on_lists", f"{olid(d['key'])} is on {n} list{'s' if n != 1 else ''}.", key=d["key"]))
        changes = _changes_for(d["key"], limit=20)
        if any(c.author and not BOT_AUTHOR.search(olid(c.author.key)) for c in changes):
            out.append(_w("info", "human_edited", f"{olid(d['key'])} has been edited by a person.", key=d["key"]))
    return out


def check_merge_editions(docs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    items = [d for d in docs.values() if doc_type(d) == "/type/edition"]
    works = {tuple(sorted(ref_keys(d.get("works")))) for d in items}
    if len(works) > 1:
        out.append(_w("block", "different_works", "The editions belong to different works; merge the works first."))
    isbns = [set((d.get("isbn_13") or []) + (d.get("isbn_10") or [])) for d in items]
    non_empty = [s for s in isbns if s]
    if len(non_empty) > 1 and not set.intersection(*non_empty):
        out.append(_w("warn", "different_isbns", "The editions share no ISBN; make sure they are the same printing."))
    scans = {str(d["ocaid"]) for d in items if d.get("ocaid")}
    if len(scans) > 1:
        out.append(_w("warn", "multiple_scans", "More than one edition has a scan; only one ocaid survives a merge (" + ", ".join(sorted(scans)) + ")."))
    fmts = {(d.get("physical_format") or "").lower() for d in items} - {""}
    if len(fmts) > 1:
        out.append(_w("warn", "different_formats", "Physical formats differ: " + ", ".join(sorted(fmts))))
    return out


def checks_for(action: str, docs: dict[str, dict[str, Any]], params: dict[str, Any], extra: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    extra = extra or {}
    try:
        if action == "merge_authors":
            return check_merge_authors(docs)
        if action == "merge_works":
            return check_merge_works(docs)
        if action == "move_editions":
            return check_move_editions(docs, extra.get("target"))
        if action == "set_author":
            return check_set_author(docs, extra.get("author"), bool(params.get("include_editions")))
        if action == "tag":
            return check_tag(docs, params.get("add") or {})
        if action in ("flag", "delete"):
            return check_flag_or_delete(docs)
        if action == "merge_editions":
            return check_merge_editions(docs)
    except Exception:
        logger.exception("preview check failed for %s", action)
        return [_w("info", "check_failed", "Some checks couldn't run; nothing was verified automatically.")]
    return []


# ── Duplicate candidates ─────────────────────────────────────────────


def _solr_select(query: str, fields: list[str], rows: int = 10) -> list[dict[str, Any]]:
    try:
        from openlibrary.plugins.worksearch.search import get_solr

        result = get_solr().select(query, fields=fields, rows=rows)
        return [dict(d) for d in result.get("docs", [])]
    except Exception:
        logger.warning("solr select failed: %s", query, exc_info=True)
        return []


def _escape(s: str) -> str:
    return re.sub(r'([+\-!(){}\[\]^"~*?:\\/&|])', r"\\\1", s)


def duplicates_for(key: str) -> dict[str, Any]:
    """Likely duplicates of a work or author, from Solr, for the “find duplicates of this” query."""
    rkey, doc, _chain = resolve_key(key)
    if not doc:
        return {"key": key, "candidates": []}
    rtype = TYPE_BY_TYPEKEY.get(doc_type(doc) or "")
    fields = ["key", "title", "name", "author_name", "first_publish_year", "edition_count", "work_count", "birth_date", "death_date", "top_work", "cover_i"]
    cands: list[dict[str, Any]] = []
    if rtype == "work":
        title = _escape(doc.get("title") or "")
        authors = resolved_ref_keys(doc.get("authors"))
        q = f'type:work AND title:"{title}"'
        if authors:
            q += " AND author_key:(" + " OR ".join(olid(a) for a in authors) + ")"
        cands = _solr_select(q, fields, rows=25)
    elif rtype == "author":
        name = _escape(doc.get("name") or "")
        q = f'type:author AND (name:"{name}" OR alternate_names:"{name}")'
        cands = _solr_select(q, fields, rows=25)
    elif rtype == "edition":
        isbns = (doc.get("isbn_13") or []) + (doc.get("isbn_10") or [])
        if isbns:
            q = "type:work AND isbn:(" + " OR ".join(_escape(i) for i in isbns) + ")"
            cands = _solr_select(q, fields, rows=25)
    cands = [c for c in cands if c.get("key") != rkey]
    return {"key": rkey, "type": rtype, "title": doc.get("title") or doc.get("name"), "candidates": cands}


duplicates_for_cached = cache.memcache_memoize(duplicates_for, key_prefix="librarians.duplicates", timeout=2 * cache.MINUTE_SECS)
