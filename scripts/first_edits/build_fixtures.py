#!/usr/bin/env python
"""Build First Edits fixtures from real books with real gaps.

Finds popular editions on openlibrary.org whose records are missing a field
or hold a value worth checking, asks outside catalogs what they say, keeps the
editions where that evidence makes a task under the current scope, and writes
them as fixtures. Optionally imports the same editions into the local dev site
so the walkthrough shows them.

Sources: HathiTrust's Bib API (MARC-XML by ISBN, no key) and, when
GOOGLE_BOOKS_API_KEY is set or the keyless quota allows, Google Books. The
Library of Congress SRU endpoint the plan named (lx2.loc.gov) no longer
answers, so LoC records arrive through HathiTrust, which carries the LCCN.

Run inside the web container, which has the MARC parser and reaches the
local site:

    docker compose exec web python scripts/first_edits/build_fixtures.py --count 50 --import-local
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests
import web
from lxml import etree

from openlibrary.catalog.marc.marc_xml import MarcXml
from openlibrary.catalog.marc.parse import read_edition
from openlibrary.first_edits.evidence import build_field_evidence
from openlibrary.first_edits.scope import load_scope

FIXTURES = Path(__file__).resolve().parents[2] / "openlibrary" / "first_edits" / "fixtures"
UA = {"User-Agent": "openlibrary-first-edits-fixtures/0.1 (https://openlibrary.org; dev tooling)"}
PROD = "https://openlibrary.org"
MARC_NS = "{http://www.loc.gov/MARC21/slim}"

# Broad enough to reach past the usual suspects; sorted by reading-log count so the books matter.
QUERIES = (
    "subject:history",
    "subject:science",
    "subject:biography",
    "subject:philosophy",
    "subject:economics",
    "subject:psychology",
    "subject:politics_and_government",
    "subject:sociology",
    "subject:american_literature",
    "subject:english_literature",
    "subject:poetry",
    "subject:mathematics",
    "subject:religion",
    "subject:art",
    "subject:music",
    "subject:natural_history",
    "subject:education",
    "subject:anthropology",
    "subject:physics",
    "subject:classics",
    "subject:fiction",
)
# HathiTrust is deepest for books libraries bought, so lean on older first publication.
YEAR_FILTER = "first_publish_year:[1800 TO 2012]"
FIELDS = ("languages", "number_of_pages", "publishers", "subtitle", "publish_date", "lccn", "oclc_numbers")
GOOGLE_LANG = {
    "en": "eng",
    "fr": "fre",
    "de": "ger",
    "es": "spa",
    "it": "ita",
    "pt": "por",
    "nl": "dut",
    "ru": "rus",
    "ja": "jpn",
    "zh": "chi",
    "pl": "pol",
    "sv": "swe",
    "tr": "tur",
}


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def get_json(url: str, **params):
    for attempt in range(3):
        try:
            r = requests.get(url, params=params or None, headers=UA, timeout=40)
            if r.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            log(f"  retry {url[:60]}: {e}")
            time.sleep(2)
    return None


# ---------------------------------------------------------------- discovery


def popular_works(per_query: int) -> list[dict]:
    seen, out = set(), []
    for q in QUERIES:
        data = get_json(
            f"{PROD}/search.json", q=f"{q} {YEAR_FILTER}", sort="readinglog", limit=per_query, fields="key,title,readinglog_count,cover_i,edition_count"
        )
        for doc in (data or {}).get("docs", []):
            if doc["key"] not in seen:
                seen.add(doc["key"])
                out.append(doc)
    out.sort(key=lambda d: -(d.get("readinglog_count") or 0))
    return out


def ol_values(ed: dict) -> dict:
    return {
        "publishers": ed.get("publishers") or [],
        "publish_date": ed.get("publish_date"),
        "number_of_pages": ed.get("number_of_pages"),
        "languages": [lang["key"].split("/")[-1] for lang in ed.get("languages") or []],
        "subtitle": ed.get("subtitle"),
        "lccn": ed.get("lccn") or [],
        "oclc_numbers": ed.get("oclc_numbers") or [],
    }


def gap_score(ed: dict) -> int:
    """How much a newcomer could add here: missing fields count most, a cover makes it presentable."""
    v = ol_values(ed)
    fmt = (ed.get("physical_format") or "").lower()
    if "audio" in fmt or "cd" in fmt or "ebook" in fmt:
        return -1
    score = sum(1 for f in ("languages", "number_of_pages", "publishers") if not v[f]) * 3
    score += sum(1 for f in ("lccn", "oclc_numbers") if not v[f])
    score += 1 if ed.get("covers") else 0
    score += 3 if ed.get("ocaid") else 0  # a scan is a second source we can always reach
    return score


def _year(ed: dict) -> int | None:
    m = re.search(r"\d{4}", ed.get("publish_date") or "")
    return int(m.group()) if m else None


def _plausible(ed: dict) -> bool:
    """English or unlabelled, printed before 2016, a title in Latin script: what HathiTrust and IA tend to hold."""
    langs = [lang["key"].split("/")[-1] for lang in ed.get("languages") or []]
    if langs and langs != ["eng"]:
        return False
    if (y := _year(ed)) and y > 2015:
        return False
    return (ed.get("title") or "").isascii()


def candidate_editions(work_key: str, per_work: int) -> list[dict]:
    data = get_json(f"{PROD}{work_key}/editions.json", limit=50)
    eds = [e for e in (data or {}).get("entries", []) if e.get("isbn_13") and _plausible(e)]
    eds = [e for e in eds if gap_score(e) > 0]
    eds.sort(key=lambda e: -gap_score(e))
    return eds[:per_work]


# ---------------------------------------------------------------- sources


def marc_fields(xml: str) -> dict:
    root = etree.fromstring(xml.encode("utf8"))
    rec = root if root.tag == f"{MARC_NS}record" else root.find(f".//{MARC_NS}record")
    ed = read_edition(MarcXml(rec))
    out: dict[str, object] = {}
    for f in FIELDS:
        if (v := ed.get(f)) not in (None, "", []):
            out[f] = v
    return out


def hathitrust(isbn13: str, ed: dict | None = None) -> dict | None:
    """By ISBN first; older printings are often catalogued under OCLC or LCCN instead, so fall back to those."""
    lookups = [("isbn", isbn13)]
    for fld, kind in (("oclc_numbers", "oclc"), ("lccn", "lccn")):
        if ed and (ids := ed.get(fld)):
            lookups.append((kind, str(ids[0]).strip()))
    data = None
    for kind, value in lookups:
        data = get_json(f"https://catalog.hathitrust.org/api/volumes/full/{kind}/{quote(value)}.json")
        if data and data.get("records"):
            break
        time.sleep(0.5)
    if not data or not data.get("records"):
        return None
    # Prefer the record that lists this exact ISBN; HathiTrust clusters printings.
    recs = list(data["records"].items())
    recs.sort(key=lambda kv: 0 if isbn13 in (kv[1].get("isbns") or []) else 1)
    rid, rec = recs[0]
    try:
        fields = marc_fields(rec["marc-xml"])
    except Exception as e:  # noqa: BLE001 - a bad record just means no evidence from this source
        log(f"  hathitrust marc parse failed for {isbn13}: {e}")
        return None
    return {"id": "hathitrust", "match": "isbn13", "url": rec.get("recordURL") or f"https://catalog.hathitrust.org/Record/{rid}", "fields": fields}


IA_LANG = {"english": "eng", "french": "fre", "german": "ger", "spanish": "spa", "italian": "ita"}


def ia_scan(ocaid: str) -> dict | None:
    """The scanned copy's own record. Edition-level by nature: it is one physical book."""
    data = get_json(f"https://archive.org/metadata/{ocaid}/metadata")
    m = (data or {}).get("result") or {}
    if not m:
        return None
    fields: dict[str, object] = {}
    if pub := m.get("publisher"):
        pub = pub if isinstance(pub, str) else pub[0]
        fields["publishers"] = [pub.split(" : ", 1)[1].strip() if " : " in pub else pub.strip()]
    if date := m.get("date"):
        fields["publish_date"] = date if isinstance(date, str) else date[0]
    lang = m.get("language")
    lang = lang[0] if isinstance(lang, list) else lang
    if lang:
        code = IA_LANG.get(lang.lower(), lang.lower())
        if len(code) == 3:
            fields["languages"] = [code]
    if lccn := m.get("lccn"):
        fields["lccn"] = [lccn] if isinstance(lccn, str) else list(lccn)
    if oclc := m.get("oclc-id"):
        fields["oclc_numbers"] = [oclc] if isinstance(oclc, str) else list(oclc)
    return {"id": "ia", "match": "ocaid", "url": f"https://archive.org/details/{ocaid}", "fields": fields} if fields else None


def google_books(isbn13: str, key: str | None) -> dict | None:
    params = {"q": f"isbn:{isbn13}"}
    if key:
        params["key"] = key
    data = get_json("https://www.googleapis.com/books/v1/volumes", **params)
    items = (data or {}).get("items") or []
    if len(items) != 1:
        return None
    vi = items[0].get("volumeInfo", {})
    fields: dict[str, object] = {}
    if vi.get("publisher"):
        fields["publishers"] = [vi["publisher"]]
    if vi.get("publishedDate"):
        fields["publish_date"] = vi["publishedDate"]
    if vi.get("pageCount"):
        fields["number_of_pages"] = vi["pageCount"]
    if (lang := GOOGLE_LANG.get(vi.get("language", ""))) is not None:
        fields["languages"] = [lang]
    if vi.get("subtitle"):
        fields["subtitle"] = vi["subtitle"]
    url = vi.get("infoLink") or f"https://books.google.com/books?vid=ISBN{isbn13}"
    return {"id": "googlebooks", "match": "isbn13", "url": url, "fields": fields}


# ---------------------------------------------------------------- tasks


def tasks_for(values: dict, doc: dict) -> list[tuple[str, str, str]]:
    """(field, mode, level) for every field the scope would offer, using the site's own rule."""
    scope = load_scope()
    out = []
    for fld in scope.enabled_fields():
        ev = build_field_evidence(fld, values, doc)
        if ev.mode and scope.fields[fld].allows(ev.mode, ev.level):
            out.append((fld, ev.mode, ev.level))
    return out


def note_for(tasks: list[tuple[str, str, str]]) -> str:
    names = {
        "languages": "language",
        "number_of_pages": "page count",
        "publishers": "publisher",
        "lccn": "LCCN",
        "oclc_numbers": "OCLC",
        "publish_date": "date",
        "subtitle": "subtitle",
    }
    return "; ".join(f"{names[f]} {'missing' if m == 'fill' else 'differs'} ({lvl} {m})" for f, m, lvl in tasks)


# ---------------------------------------------------------------- local import

_author_names: dict[str, str] = {}


def author_names(keys: list[str]) -> list[dict]:
    out = []
    for k in keys:
        if k not in _author_names:
            data = get_json(f"{PROD}{k}.json") or {}
            _author_names[k] = data.get("name") or ""
        if _author_names[k]:
            out.append({"name": _author_names[k]})
    return out


def import_payload(ed: dict, work: dict) -> dict:
    """Production's fields, no more: the gaps are the point."""
    authors = author_names([a.get("author", a).get("key") for a in ed.get("authors") or work.get("authors") or [] if a.get("author", a).get("key")])
    p = {"title": ed.get("title"), "authors": authors, "isbn_13": ed.get("isbn_13"), "source_records": [f"first-edits-demo:{ed['isbn_13'][0]}"]}
    for f in ("subtitle", "publishers", "publish_date", "number_of_pages", "isbn_10", "lccn", "oclc_numbers", "physical_format"):
        if ed.get(f) not in (None, "", []):
            p[f] = ed[f]
    if ed.get("languages"):
        p["languages"] = [lang["key"].split("/")[-1] for lang in ed["languages"]]
    return p


class LocalSite:
    def __init__(self, base: str, username: str, password: str):
        self.base = base
        self.s = requests.Session()
        r = self.s.post(f"{base}/account/login.json", json={"username": username, "password": password}, timeout=30)
        r.raise_for_status()

    def import_edition(self, payload: dict) -> str:
        r = self.s.post(f"{self.base}/api/import", json=payload, timeout=120)
        try:
            data = r.json()
        except ValueError:
            data = {"error": r.text[:200]}
        if r.status_code != 200 or not data.get("edition"):
            return f"FAILED {r.status_code} {data.get('error') or data}"
        return data["edition"]["key"]


# ---------------------------------------------------------------- main


def main() -> int:
    web.ctx.lang = "en"  # gettext in the evidence builder wants a request language
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count", type=int, default=50, help="editions to keep")
    ap.add_argument("--per-query", type=int, default=25)
    ap.add_argument("--per-work", type=int, default=3)
    ap.add_argument("--import-local", action="store_true", help="import kept editions (and some siblings) into the local site")
    ap.add_argument("--siblings", type=int, default=3, help="other editions of each work to import for sibling counts")
    ap.add_argument("--local", default="http://localhost:8080")
    ap.add_argument("--user", default="openlibrary")
    ap.add_argument("--password", default="openlibrary")
    ap.add_argument("--dry-run", action="store_true", help="discover and query, write nothing")
    args = ap.parse_args()

    google_key = os.environ.get("GOOGLE_BOOKS_API_KEY")
    demo_path = FIXTURES / "demo_books.json"
    demo = json.loads(demo_path.read_text()) if demo_path.exists() else []
    have = {d["isbn13"] for d in demo}

    works = popular_works(args.per_query)
    log(f"{len(works)} popular works to look through")
    kept: list[dict] = []
    google_dead = False
    local = LocalSite(args.local, args.user, args.password) if args.import_local and not args.dry_run else None

    for work in works:
        if len(kept) >= args.count:
            break
        work_full = None
        for ed in candidate_editions(work["key"], args.per_work):
            if len(kept) >= args.count:
                break
            isbn = ed["isbn_13"][0]
            if isbn in have:
                continue
            time.sleep(1.0)  # one request a second to HathiTrust
            sources = [s for s in [hathitrust(isbn, ed), ia_scan(ed["ocaid"]) if ed.get("ocaid") else None] if s]
            if not google_dead:
                g = google_books(isbn, google_key)
                if g is None and not google_key:
                    google_dead = True  # keyless quota is per day; stop asking
                    log("  google books: no answer without a key, continuing with HathiTrust only")
                elif g:
                    sources.append(g)
            if not sources:
                continue
            doc = {"isbn13": isbn, "built": time.strftime("%Y-%m-%d"), "sources": sources}
            tasks = tasks_for(ol_values(ed), doc)
            if not tasks:
                continue
            entry = {
                "isbn13": isbn,
                "key": ed["key"],
                "readers": work.get("readinglog_count") or 0,
                "note": f"{work.get('title', '')[:40]}: {note_for(tasks)}",
                "cover_id": (ed.get("covers") or [None])[0] or work.get("cover_i"),
            }
            log(f"keep {ed['key']} {isbn} {work.get('title', '')[:40]!r} -> {entry['note'].split(': ', 1)[1]}")
            if not args.dry_run:
                (FIXTURES / "evidence" / f"{isbn}.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
                demo.append(entry)
                have.add(isbn)
            kept.append(entry)
            if local:
                work_full = work_full or get_json(f"{PROD}{work['key']}.json") or {}
                log(f"  import {local.import_edition(import_payload(ed, work_full))}")
                others = [
                    e
                    for e in (get_json(f"{PROD}{work['key']}/editions.json", limit=30) or {}).get("entries", [])
                    if e.get("isbn_13") and e["key"] != ed["key"] and e.get("publishers") and e.get("publish_date")
                ]
                for sib in others[: args.siblings]:
                    time.sleep(0.3)
                    log(f"  sibling {local.import_edition(import_payload(sib, work_full))}")

    if not args.dry_run:
        demo.sort(key=lambda d: -d.get("readers", 0))
        demo_path.write_text(json.dumps(demo, indent=2, ensure_ascii=False) + "\n")
    log(f"kept {len(kept)} editions; demo set now {len(demo)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
