"""The librarian workbench: a Solr query over editions, works or authors, the
rows hydrated from the database with health chips, and worklists (saved
queries shared between librarians).

Solr answers *which* records; the database answers *what is on them*. A page
of rows costs one Solr select plus at most three ``get_many`` calls (the rows,
their works, their authors), so the grid stays cheap no matter which columns
are showing. Anything that needs edit history or external lookups belongs in
``record_context.health`` for the one record the panel shows.

Everything here reads; batch_ops writes.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from openlibrary.core import cache
from openlibrary.core.record_context import (
    LOW_TRUST_SOURCES,
    ROLE_WORDS,
    RecordType,
    key_type,
    load_docs,
    normalize_key,
    olid,
    parse_source,
    ref_keys,
    year_of,
)
from openlibrary.utils.request_context import site

logger = logging.getLogger("openlibrary.workbench")

MAX_ROWS = 100
Scope = Literal["solr", "page"]

UNIVERSE: dict[RecordType, str] = {"edition": "type:edition", "work": "type:work", "author": "type:author"}

# What the grid asks Solr for; the database fills in the rest per row.
SOLR_FIELDS: dict[RecordType, list[str]] = {
    "edition": [
        "key",
        "work_key",
        "title",
        "subtitle",
        "author_name",
        "author_key",
        "publisher",
        "publish_date",
        "publish_year",
        "isbn",
        "language",
        "ia",
        "cover_i",
        "format",
        "ebook_access",
    ],
    "work": [
        "key",
        "title",
        "subtitle",
        "author_name",
        "author_key",
        "first_publish_year",
        "edition_count",
        "language",
        "cover_i",
        "ebook_access",
        "subject",
        "last_modified_i",
        "readinglog_count",
    ],
    "author": ["key", "name", "birth_date", "death_date", "work_count", "top_work", "top_subjects"],
}

# Free text (no field:value syntax) searches these.
QF: dict[RecordType, str] = {
    "edition": "title^3 subtitle author_name^2 publisher isbn lccn oclc ia key",
    "work": "title^3 subtitle author_name^2 subject key",
    "author": "name^3 alternate_names top_work key",
}

SORTS: dict[RecordType, dict[str, str]] = {
    "edition": {
        "relevance": "score desc",
        "year_desc": "publish_year desc",
        "year_asc": "publish_year asc",
        "title": "title_sort asc",
        "usefulness": "usefulness_score desc",
    },
    "work": {
        "relevance": "score desc",
        "year_desc": "first_publish_year desc",
        "year_asc": "first_publish_year asc",
        "title": "title_sort asc",
        "editions_desc": "edition_count desc",
        "editions_asc": "edition_count asc",
        "modified": "last_modified_i desc",
        "readers": "readinglog_count desc",
    },
    "author": {
        "relevance": "score desc",
        "works_desc": "work_count desc",
        "works_asc": "work_count asc",
        "name": "name_sort asc",
        "born_asc": "birth_date asc",
        "born_desc": "birth_date desc",
    },
}


# ── Filters ──────────────────────────────────────────────────────────
#
# A filter is a named Solr fq (scope "solr") or a health check computed on the
# hydrated page (scope "page": the count in the rail is the page's, not the
# index's, and the client says so). `value` names the input the filter takes.


def _fq(template: str, **kw: Any) -> str:
    return template.format(**kw)


FILTERS: dict[str, dict[str, Any]] = {
    # Values
    "language": {"label": "Language", "types": ["edition", "work"], "value": "text", "fq": 'language:"{v}"'},
    "publisher": {"label": "Publisher", "types": ["edition", "work"], "value": "text", "fq": 'publisher:"{v}"'},
    "author": {"label": "Author OLID", "types": ["edition", "work"], "value": "text", "fq": "author_key:{v}"},
    "format": {"label": "Format", "types": ["edition"], "value": "text", "fq": 'format:"{v}"'},
    "year": {"label": "Year", "types": ["edition"], "value": "range", "fq": "publish_year:[{a} TO {b}]"},
    "first_year": {"label": "First published", "types": ["work"], "value": "range", "fq": "first_publish_year:[{a} TO {b}]"},
    "editions": {"label": "Edition count", "types": ["work"], "value": "range", "fq": "edition_count:[{a} TO {b}]"},
    "works": {"label": "Work count", "types": ["author"], "value": "range", "fq": "work_count:[{a} TO {b}]"},
    "access": {
        "label": "Ebook access",
        "types": ["edition", "work"],
        "value": "enum",
        "options": ["public", "borrowable", "printdisabled", "no_ebook"],
        "fq": "ebook_access:{v}",
    },
    "modified_days": {"label": "Modified in the last N days", "types": ["work"], "value": "int", "fq": "last_modified_i:[{epoch} TO *]"},
    # Gaps
    "has_scan": {"label": "Has a scan", "types": ["edition", "work"], "fq": "ia:*"},
    "no_scan": {"label": "No scan", "types": ["edition", "work"], "fq": "-ia:*"},
    "no_cover": {"label": "No cover", "types": ["edition", "work"], "fq": "-cover_i:*"},
    "no_isbn": {"label": "No ISBN", "types": ["edition"], "fq": "-isbn:*"},
    "no_language": {"label": "No language", "types": ["edition", "work"], "fq": "-language:*"},
    "no_publisher": {"label": "No publisher", "types": ["edition"], "fq": "-publisher:*"},
    "no_year": {"label": "No publish year", "types": ["edition"], "fq": "-publish_year:*"},
    "no_first_year": {"label": "No first publish year", "types": ["work"], "fq": "-first_publish_year:*"},
    "no_author": {"label": "No author", "types": ["work"], "fq": "-author_key:*"},
    "no_subject": {"label": "No subjects", "types": ["work"], "fq": "-subject:*"},
    "no_editions": {"label": "No editions", "types": ["work"], "fq": "edition_count:0"},
    "one_edition": {"label": "Exactly one edition", "types": ["work"], "fq": "edition_count:1"},
    "orphan_works": {"label": "Orphaned editions (indexed as works)", "types": ["work"], "fq": "key:*M"},
    "no_ddc": {"label": "No Dewey class", "types": ["work"], "fq": "-ddc:*"},
    "no_lcc": {"label": "No LC class", "types": ["work"], "fq": "-lcc:*"},
    "no_pages": {"label": "No page count", "types": ["work"], "fq": "-number_of_pages_median:*"},
    "no_dates": {"label": "No birth or death date", "types": ["author"], "fq": "-birth_date:* AND -death_date:*"},
    "no_works": {"label": "No works", "types": ["author"], "fq": "work_count:0"},
    # Health, computed on the page
    "author_mismatch": {"label": "Edition author ≠ work author", "types": ["edition"], "scope": "page"},
    "low_trust": {"label": "Low-trust import", "types": ["edition"], "scope": "page"},
    "future_date": {"label": "Future publish date", "types": ["edition"], "scope": "page"},
    "orphan_edition": {"label": "No work", "types": ["edition"], "scope": "page"},
    "no_identifiers": {"label": "No ISBN, LCCN, OCLC or scan", "types": ["edition"], "scope": "page"},
    "placeholder_cover": {"label": "Placeholder cover", "types": ["edition"], "scope": "page"},
    "no_authors": {"label": "No authors on the record", "types": ["work"], "scope": "page"},
    "role_in_name": {"label": "Role word in the name", "types": ["author"], "scope": "page"},
    "no_strong_ids": {"label": "No Wikidata, VIAF, LC or ISNI id", "types": ["author"], "scope": "page"},
}


class WorkbenchError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def _check_type(rtype: str) -> RecordType:
    if rtype not in UNIVERSE:
        raise WorkbenchError(f"Unknown record type {rtype!r}.")
    return rtype  # type: ignore[return-value]


def public_filters() -> list[dict[str, Any]]:
    return [{"id": k, "scope": v.get("scope", "solr"), **{x: v[x] for x in ("label", "types", "value", "options") if x in v}} for k, v in FILTERS.items()]


def split_filters(rtype: RecordType, filters: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """Filters → (Solr fq clauses, page-scope check codes). Unknown ids are dropped."""
    fqs: list[str] = []
    page: list[str] = []
    for f in filters or []:
        fid = f.get("id") if isinstance(f, dict) else str(f)
        spec = FILTERS.get(fid) if fid else None
        if not fid or not spec or rtype not in spec["types"]:
            continue
        if spec.get("scope") == "page":
            page.append(fid)
            continue
        value = f.get("value") if isinstance(f, dict) else None
        kind = spec.get("value")
        if kind == "range":
            a, b = _range(value)
            fqs.append(_fq(spec["fq"], a=a, b=b))
        elif kind == "int":
            n = int(value or 0)
            epoch = int(datetime.now(UTC).timestamp()) - max(n, 0) * 86400
            fqs.append(_fq(spec["fq"], epoch=epoch))
        elif kind in ("text", "enum"):
            v = str(value or "").strip()
            if not v or (kind == "enum" and v not in spec["options"]):
                continue
            if fid == "author":
                v = olid(normalize_key(v) or "") or v
            fqs.append(_fq(spec["fq"], v=_escape(v) if kind == "text" else v))
        else:
            fqs.append(spec["fq"])
    return fqs, page


def _range(value: Any) -> tuple[str, str]:
    a, b = "*", "*"
    if isinstance(value, dict):
        a = str(int(value["from"])) if value.get("from") not in (None, "") else "*"
        b = str(int(value["to"])) if value.get("to") not in (None, "") else "*"
    elif isinstance(value, str) and value:
        parts = value.replace("\u2013", "-").split("-", 1)
        a = parts[0].strip() or "*"
        b = (parts[1].strip() if len(parts) > 1 else parts[0].strip()) or "*"
        a, b = (str(int(a)) if a != "*" else a), (str(int(b)) if b != "*" else b)
    return a, b


def _escape(s: str) -> str:
    return re.sub(r'(["\\])', r"\\\1", s)


# ── Query ────────────────────────────────────────────────────────────


def _is_fielded(q: str) -> bool:
    """`author_key:OL1A`, `title:"x" AND -ia:*` are Lucene; `tolkien hobbit` is free text."""
    return bool(re.search(r"(^|\s|\()[-+]?[a-z_][a-z_0-9.]*:", q, re.IGNORECASE)) or bool(re.search(r"\b(AND|OR|NOT)\b|[*\[\]{}~^]", q))


def _solr_params(rtype: RecordType, q: str, fqs: list[str], sort: str, rows: int, start: int) -> dict[str, Any]:
    q = (q or "").strip()
    params: dict[str, Any] = {
        "fq": [UNIVERSE[rtype], *fqs],
        "fl": ",".join(SOLR_FIELDS[rtype]),
        "rows": rows,
        "start": start,
        "sort": SORTS[rtype].get(sort) or SORTS[rtype]["relevance"],
    }
    if not q:
        params["q"] = "*:*"
        if params["sort"] == "score desc":
            params["sort"] = next(iter(SORTS[rtype].values())) if rtype == "author" else SORTS[rtype]["title"]
    elif _is_fielded(q):
        params["q"] = q
        params["q.op"] = "AND"
    else:
        params["q"] = q
        params["defType"] = "edismax"
        params["qf"] = QF[rtype]
        params["q.op"] = "AND"
    return params


def _solr():
    from openlibrary.plugins.worksearch.search import get_solr

    return get_solr()


def _solr_error(e: Exception) -> str:
    """Solr's own message for a bad query, when the HTTP error carries one."""
    resp = getattr(e, "response", None)
    try:
        msg = (resp.json().get("error") or {}).get("msg") if resp is not None else None
    except Exception:  # noqa: BLE001
        msg = None
    return msg or str(e)


def _select(params: dict[str, Any]) -> dict[str, Any]:
    """One Solr select. ``params`` uses Solr's own names; the client maps ``q_op`` → ``q.op``."""
    p = dict(params)
    q = p.pop("q")
    fields = p.pop("fl", None)
    kw = {("q_op" if k == "q.op" else k): v for k, v in p.items()}
    result = _solr().select(q, fields=fields.split(",") if fields else None, doc_wrapper=dict, **kw)
    return {"docs": list(result.docs), "num_found": result.num_found}


def run_query(rtype: str, q: str = "", filters: list[dict[str, Any]] | None = None, sort: str = "relevance", page: int = 1, rows: int = 50) -> dict[str, Any]:
    """One page of the grid: Solr picks the records, the database fills the rows."""
    rt = _check_type(rtype)
    rows = max(1, min(int(rows or 50), MAX_ROWS))
    page = max(1, int(page or 1))
    fqs, page_checks = split_filters(rt, filters or [])
    params = _solr_params(rt, q, fqs, sort, rows, (page - 1) * rows)
    try:
        result = _select(params)
    except Exception as e:
        logger.warning("workbench solr query failed: %s", params, exc_info=True)
        raise WorkbenchError(f"Search failed: {_solr_error(e)}", 400) from e
    keys = [d["key"] for d in result["docs"] if d.get("key")]
    hydrated = hydrate(rt, keys, solr_docs=result["docs"])
    if page_checks:
        wanted = set(page_checks)
        hydrated = [r for r in hydrated if wanted & {c["code"] for c in r["chips"]}]
    return {
        "type": rt,
        "q": q,
        "filters": filters or [],
        "page_filters": page_checks,
        "sort": sort if sort in SORTS[rt] else "relevance",
        "page": page,
        "rows": rows,
        "num_found": result["num_found"],
        "records": hydrated,
        "solr": {"q": params["q"], "fq": params["fq"], "sort": params["sort"]},
    }


def count_query(rtype: str, q: str = "", filters: list[dict[str, Any]] | None = None) -> int | None:
    rt = _check_type(rtype)
    fqs, _page = split_filters(rt, filters or [])
    params = _solr_params(rt, q, fqs, "relevance", 0, 0)
    params.pop("fl", None)
    params.pop("sort", None)
    try:
        return _select(params)["num_found"]
    except Exception:
        logger.warning("workbench count failed", exc_info=True)
        return None


count_query_cached = cache.memcache_memoize(count_query, key_prefix="workbench.count", timeout=5 * cache.MINUTE_SECS, hash_args=True)


# ── Hydration ────────────────────────────────────────────────────────


def _names(keys: list[str], authors: dict[str, dict[str, Any]], resolved: dict[str, str]) -> list[dict[str, Any]]:
    out = []
    for k in keys:
        rk = resolved.get(k, k)
        a = authors.get(rk)
        out.append({"key": rk, "name": (a or {}).get("name") or olid(rk)})
    return out


def _cover(cover_id: int | None, rtype: RecordType, key: str) -> str | None:
    if cover_id and cover_id > 0:
        return f"https://covers.openlibrary.org/{'a' if rtype == 'author' else 'b'}/id/{cover_id}-S.jpg"
    return None


def _chip(code: str, level: str, text: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "level": level, "text": text, **extra}


def _provenance(doc: dict[str, Any]) -> tuple[list[str], bool]:
    sources = doc.get("source_records") or []
    prefixes = sorted({parse_source(s)[0] for s in sources})
    low_trust = bool(prefixes) and set(prefixes) <= LOW_TRUST_SOURCES
    return prefixes, low_trust


def _edition_row(
    doc: dict[str, Any], sd: dict[str, Any], works: dict[str, dict[str, Any]], authors: dict[str, dict[str, Any]], resolved: dict[str, str]
) -> dict[str, Any]:
    key = doc["key"]
    work_key = next(iter(ref_keys(doc.get("works"))), None)
    work_key = resolved.get(work_key, work_key) if work_key else None
    work = works.get(work_key) if work_key else None
    e_auth = [resolved.get(k, k) for k in ref_keys(doc.get("authors"))]
    w_auth = [resolved.get(k, k) for k in ref_keys((work or {}).get("authors"))]
    sources, low_trust = _provenance(doc)
    chips: list[dict[str, Any]] = []
    if e_auth and w_auth and set(e_auth).isdisjoint(w_auth):
        chips.append(_chip("author_mismatch", "block", "Author ≠ work", detail={"edition": e_auth, "work": w_auth}))
    if low_trust:
        chips.append(_chip("low_trust", "warn", "Low-trust import", detail={"sources": sources}))
    if (y := year_of(doc.get("publish_date"))) and y > datetime.now(UTC).year + 1:
        chips.append(_chip("future_date", "warn", f"Future date {y}"))
    if not work_key:
        chips.append(_chip("orphan_edition", "warn", "No work"))
    if doc.get("covers") and all(c == -1 for c in doc["covers"]):
        chips.append(_chip("placeholder_cover", "info", "Placeholder cover"))
    if not (doc.get("isbn_10") or doc.get("isbn_13") or doc.get("ocaid") or doc.get("lccn") or doc.get("oclc_numbers")):
        chips.append(_chip("no_identifiers", "info", "No identifiers"))
    covers = [c for c in doc.get("covers") or [] if c and c > 0]
    return {
        "key": key,
        "type": "edition",
        "title": doc.get("title") or "",
        "subtitle": doc.get("subtitle") or "",
        "revision": doc.get("revision"),
        "authors": _names(e_auth, authors, resolved)
        if e_auth
        else [{"key": f"/authors/{a}", "name": n, "via": "work"} for a, n in zip(sd.get("author_key") or [], sd.get("author_name") or [], strict=False)],
        "work": {"key": work_key, "title": (work or {}).get("title") or sd.get("title") or "", "authors": _names(w_auth, authors, resolved)}
        if work_key
        else None,
        "publishers": doc.get("publishers") or [],
        "publish_date": doc.get("publish_date") or "",
        "year": year_of(doc.get("publish_date")),
        "isbn": (doc.get("isbn_13") or doc.get("isbn_10") or [None])[0],
        "languages": [olid(lang) for lang in ref_keys(doc.get("languages"))],
        "ocaid": doc.get("ocaid"),
        "format": doc.get("physical_format") or "",
        "pages": doc.get("number_of_pages"),
        "cover": _cover(covers[0] if covers else sd.get("cover_i"), "edition", key),
        "sources": sources,
        "chips": chips,
    }


def _work_row(doc: dict[str, Any], sd: dict[str, Any], authors: dict[str, dict[str, Any]], resolved: dict[str, str]) -> dict[str, Any]:
    key = doc["key"]
    w_auth = [resolved.get(k, k) for k in ref_keys(doc.get("authors"))]
    chips: list[dict[str, Any]] = []
    if not w_auth:
        chips.append(_chip("no_authors", "warn", "No authors"))
    if sd.get("edition_count") == 0:
        chips.append(_chip("no_editions", "warn", "No editions"))
    if key.endswith("M"):
        chips.append(_chip("orphan_work", "warn", "Orphaned edition"))
    covers = [c for c in doc.get("covers") or [] if c and c > 0]
    subjects = doc.get("subjects") or []
    return {
        "key": key,
        "type": "work",
        "title": doc.get("title") or "",
        "subtitle": doc.get("subtitle") or "",
        "revision": doc.get("revision"),
        "authors": _names(w_auth, authors, resolved),
        "year": sd.get("first_publish_year"),
        "edition_count": sd.get("edition_count"),
        "languages": sd.get("language") or [],
        "subjects": subjects[:6],
        "subject_count": len(subjects),
        "readinglog_count": sd.get("readinglog_count"),
        "modified": datetime.fromtimestamp(sd["last_modified_i"], UTC).date().isoformat() if sd.get("last_modified_i") else None,
        "cover": _cover(covers[0] if covers else sd.get("cover_i"), "work", key),
        "chips": chips,
    }


def _author_row(doc: dict[str, Any], sd: dict[str, Any]) -> dict[str, Any]:
    key = doc["key"]
    ids = doc.get("remote_ids") or {}
    strong = [k for k in ("wikidata", "viaf", "lc_naf", "isni") if ids.get(k)]
    chips: list[dict[str, Any]] = []
    if ROLE_WORDS.search(doc.get("name") or ""):
        chips.append(_chip("role_in_name", "warn", "Role word in name"))
    if not strong:
        chips.append(_chip("no_strong_ids", "info", "No strong IDs"))
    photos = [p for p in doc.get("photos") or [] if p and p > 0]
    return {
        "key": key,
        "type": "author",
        "title": doc.get("name") or "",
        "revision": doc.get("revision"),
        "birth_date": doc.get("birth_date") or "",
        "death_date": doc.get("death_date") or "",
        "work_count": sd.get("work_count"),
        "top_work": sd.get("top_work") or "",
        "top_subjects": (sd.get("top_subjects") or [])[:5],
        "ids": {k: ids[k] for k in strong},
        "alternate_names": len(doc.get("alternate_names") or []),
        "cover": _cover(photos[0] if photos else None, "author", key),
        "chips": chips,
    }


def hydrate(rtype: str, keys: list[str], solr_docs: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Rows for the grid, in the order of ``keys``. Missing records are skipped."""
    rt = _check_type(rtype)
    if not keys:
        return []
    by_solr = {d.get("key"): d for d in solr_docs or []}
    docs, resolved, _missing = load_docs(keys)
    works: dict[str, dict[str, Any]] = {}
    author_keys: set[str] = set()
    if rt == "edition":
        work_keys = sorted({wk for d in docs.values() for wk in ref_keys(d.get("works"))[:1]})
        if work_keys:
            works, wres, _m = load_docs(work_keys)
            resolved.update(wres)
        for d in list(docs.values()) + list(works.values()):
            author_keys.update(ref_keys(d.get("authors")))
    elif rt == "work":
        for d in docs.values():
            author_keys.update(ref_keys(d.get("authors")))
    authors: dict[str, dict[str, Any]] = {}
    if author_keys:
        authors, ares, _m = load_docs(sorted(author_keys))
        resolved.update(ares)
    out = []
    for key in keys:
        rk = resolved.get(key, key)
        doc = docs.get(rk)
        if not doc:
            continue
        sd = by_solr.get(key) or by_solr.get(rk) or {}
        if rt == "edition":
            out.append(_edition_row(doc, sd, works, authors, resolved))
        elif rt == "work":
            out.append(_work_row(doc, sd, authors, resolved))
        else:
            out.append(_author_row(doc, sd))
    return out


def hydrate_keys(keys: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Pasted OLIDs, grouped by type, each group hydrated with a Solr lookup for its counts."""
    groups: dict[RecordType, list[str]] = {"edition": [], "work": [], "author": []}
    for k in keys:
        if (nk := normalize_key(k)) and (t := key_type(nk)):
            groups[t].append(nk)
    out: dict[str, list[dict[str, Any]]] = {}
    for rt, ks in groups.items():
        if not ks:
            continue
        solr_docs: list[dict[str, Any]] = []
        try:
            q = " OR ".join(f'"{k}"' for k in ks[:MAX_ROWS])
            solr_docs = _select({"q": f"key:({q})", "fq": [UNIVERSE[rt]], "fl": ",".join(SOLR_FIELDS[rt]), "rows": len(ks[:MAX_ROWS])})["docs"]
        except Exception:
            logger.warning("workbench key lookup failed", exc_info=True)
        out[rt] = hydrate(rt, ks[:MAX_ROWS], solr_docs=solr_docs)
    return out


# ── Worklists ────────────────────────────────────────────────────────

STORE_TYPE = "librarian-worklist"
MAX_WORKLISTS = 200

BUILTIN_WORKLISTS: list[dict[str, Any]] = [
    {"id": "no-cover-editions", "name": "Editions without a cover", "type": "edition", "q": "", "filters": [{"id": "no_cover"}], "sort": "usefulness"},
    {"id": "no-isbn-editions", "name": "Editions without an ISBN", "type": "edition", "q": "", "filters": [{"id": "no_isbn"}], "sort": "usefulness"},
    {"id": "no-language-editions", "name": "Editions without a language", "type": "edition", "q": "", "filters": [{"id": "no_language"}], "sort": "usefulness"},
    {
        "id": "no-publisher-editions",
        "name": "Editions without a publisher",
        "type": "edition",
        "q": "",
        "filters": [{"id": "no_publisher"}],
        "sort": "usefulness",
    },
    {"id": "works-no-author", "name": "Works without an author", "type": "work", "q": "", "filters": [{"id": "no_author"}], "sort": "readers"},
    {"id": "works-no-editions", "name": "Works without editions", "type": "work", "q": "", "filters": [{"id": "no_editions"}], "sort": "modified"},
    {"id": "works-no-subject", "name": "Works without subjects", "type": "work", "q": "", "filters": [{"id": "no_subject"}], "sort": "readers"},
    {"id": "orphan-works", "name": "Orphaned editions", "type": "work", "q": "", "filters": [{"id": "orphan_works"}], "sort": "modified"},
    {"id": "authors-no-works", "name": "Authors without works", "type": "author", "q": "", "filters": [{"id": "no_works"}], "sort": "name"},
    {"id": "authors-no-dates", "name": "Authors without dates", "type": "author", "q": "", "filters": [{"id": "no_dates"}], "sort": "works_desc"},
]


def _wl_key(wid: str) -> str:
    return f"/librarians/worklists/{wid}"


def _clean_worklist(body: dict[str, Any], owner: str, wid: str | None = None) -> dict[str, Any]:
    rt = _check_type(str(body.get("type") or "edition"))
    name = str(body.get("name") or "").strip()[:80]
    if not name:
        raise WorkbenchError("A worklist needs a name.")
    filters = [f for f in (body.get("filters") or []) if isinstance(f, dict) and f.get("id") in FILTERS][:20]
    sort = str(body.get("sort") or "relevance")
    return {
        "type": STORE_TYPE,
        "id": wid or uuid.uuid4().hex[:12],
        "name": name,
        "record_type": rt,
        "q": str(body.get("q") or "")[:500],
        "filters": filters,
        "sort": sort if sort in SORTS[rt] else "relevance",
        "owner": owner,
        "updated": datetime.now(UTC).replace(microsecond=0).isoformat(),
    }


def _public_worklist(doc: dict[str, Any], builtin: bool = False) -> dict[str, Any]:
    return {
        "id": doc["id"],
        "name": doc["name"],
        "type": doc.get("record_type") or doc.get("type"),
        "q": doc.get("q") or "",
        "filters": doc.get("filters") or [],
        "sort": doc.get("sort") or "relevance",
        "owner": None if builtin else doc.get("owner"),
        "builtin": builtin,
        "updated": None if builtin else doc.get("updated"),
    }


def list_worklists(with_counts: bool = False) -> list[dict[str, Any]]:
    out = [_public_worklist(w, builtin=True) for w in BUILTIN_WORKLISTS]
    try:
        saved = site.get().store.values(type=STORE_TYPE, limit=MAX_WORKLISTS)
    except Exception:
        logger.warning("worklist store read failed", exc_info=True)
        saved = []
    out.extend(_public_worklist(w) for w in sorted(saved, key=lambda w: w.get("name", "").lower()) if w.get("id"))
    if with_counts:
        for w in out:
            w["count"] = count_query_cached(w["type"], w["q"], w["filters"])
    return out


def get_worklist(wid: str) -> dict[str, Any] | None:
    for w in BUILTIN_WORKLISTS:
        if w["id"] == wid:
            return _public_worklist(w, builtin=True)
    doc = site.get().store.get(_wl_key(wid))
    return _public_worklist(doc) if doc else None


def save_worklist(owner: str, body: dict[str, Any], wid: str | None = None, is_super: bool = False) -> dict[str, Any]:
    if wid:
        existing = site.get().store.get(_wl_key(wid))
        if not existing:
            raise WorkbenchError("Worklist not found.", 404)
        if existing.get("owner") != owner and not is_super:
            raise WorkbenchError("Only the owner or a super-librarian can change this worklist.", 403)
        owner = existing.get("owner") or owner
    doc = _clean_worklist(body, owner, wid)
    site.get().store[_wl_key(doc["id"])] = doc
    return _public_worklist(doc)


def delete_worklist(owner: str, wid: str, is_super: bool = False) -> None:
    existing = site.get().store.get(_wl_key(wid))
    if not existing:
        raise WorkbenchError("Worklist not found.", 404)
    if existing.get("owner") != owner and not is_super:
        raise WorkbenchError("Only the owner or a super-librarian can delete this worklist.", 403)
    site.get().store.delete(_wl_key(wid))
