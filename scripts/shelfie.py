#!/usr/bin/env python3
"""shelfie.py - Interactive dev tool for Open Library.

Usage:
    Interactive:  python scripts/shelfie.py
    Subcommands:  python scripts/shelfie.py populate-all
                  python scripts/shelfie.py add-books --count 100
                  python scripts/shelfie.py seed-series --count 3
                  python scripts/shelfie.py set-role --username openlibrary --role admin

Run inside Docker:
    docker compose run --rm home python scripts/shelfie.py

# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------
#
# Shelfie is a CLI tool that populates a local Open Library dev environment
# with realistic data so developers can work on features without needing
# a production database dump. It runs inside the Docker Compose stack and
# talks to three internal services:
#
#   - web (port 8080):     The main OL web app. Used for authenticated
#                          operations like importing books, creating lists,
#                          and posting ratings via the OL Python client
#                          (openlibrary.api.OpenLibrary).
#
#   - infobase (port 7000): The low-level datastore. Used for direct writes
#                           that bypass web-app save bugs in local dev —
#                           e.g. updating usergroup membership and saving
#                           subjects or series docs via /save_many.
#
#   - solr (port 8983):    The search index. Queried for stats, coverage
#                          checks, and to fetch existing work keys.
#
# Data sourcing strategy:
#   Most commands fetch real data from production openlibrary.org — search
#   results, public lists, series metadata — and re-import it into the local
#   instance via the /import endpoint. This gives developers realistic titles,
#   authors, covers, subjects, and ISBNs without fabricating anything. When
#   production is unreachable, commands fall back to small bundled JSON seed
#   files in scripts/dev_data/.
#
# Two interfaces, one codebase:
#   With no arguments, shelfie launches an interactive menu (choose/ask/
#   confirm helpers) that walks the user through each operation. Every menu
#   action maps to a cmd_* function that also accepts keyword arguments, so
#   the same functions power the argparse subcommands for scripted/CI usage
#   (e.g. `shelfie add-books --count 50`).
#
# Key techniques:
#   - Import pipeline: production search doc → _search_doc_to_record()
#     normalizes fields (authors, publishers, ISBNs, cover URLs, subjects)
#     into an import-ready dict → ol.import_data() posts it to /import.
#   - Quality filtering: _is_low_quality() rejects study guides, workbooks,
#     and self-published junk so the dev DB looks like a real library.
#   - Series creation: searches production for known series titles, imports
#     the matched works, then writes /type/series docs and back-links each
#     work with a position via infobase.
#   - Reading activity: ratings, reading-log shelves (want/reading/read),
#     and lists are all posted through OL's JSON APIs as the logged-in user.
#   - Stats dashboard: cross-references infobase counts with Solr counts
#     to surface coverage gaps (works missing covers or subjects) and
#     sync drift (works not yet indexed).
#
# ---------------------------------------------------------------------------
"""

import _init_path  # noqa: F401  # isort: skip

import argparse
import contextlib
import json
import random
from pathlib import Path

import requests

from openlibrary.api import OLError, OpenLibrary

DEV_DATA_DIR = Path(__file__).parent / "dev_data"
DEFAULT_BASE_URL = "http://web:8080"
DEFAULT_INFOBASE_URL = "http://infobase:7000/openlibrary"
DEFAULT_LOGIN_EMAIL = "admin@example.com"
DEFAULT_LOGIN_PASSWORD = "admin123"
DEFAULT_USERNAME = "admin"

USERGROUPS = [
    "admin",
    "librarians",
    "super-librarians",
    "curators",
    "beta-testers",
    "read-only",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_json(filename):
    with open(DEV_DATA_DIR / filename) as f:
        return json.load(f)


def print_header(title):
    width = 50
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def print_menu(options):
    for i, label in enumerate(options, 1):
        print(f"  {i}. {label}")
    print()


class UserExit(Exception):
    """Raised when user wants to quit."""


def choose(prompt, options):
    """Prompt user to pick from a list. Returns the chosen value."""
    print_menu(options)
    while True:
        try:
            raw = input(f"{prompt} [1-{len(options)}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            raise UserExit
        if raw.lower() in ("exit", "quit", "q", "\x1b"):
            raise UserExit
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx]
        except ValueError:
            pass
        print(f"  Please enter a number between 1 and {len(options)}.")


def ask(prompt, default=""):
    """Prompt for text input with an optional default."""
    suffix = f" [{default}]" if default else ""
    try:
        raw = input(f"{prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        raise UserExit
    if raw.lower() in ("exit", "quit"):
        raise UserExit
    return raw or default


def confirm(prompt):
    try:
        return input(f"{prompt} (y/n): ").strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        raise UserExit


def connect(base_url=None, email=None, password=None):
    """Create and authenticate an OL client."""
    base_url = base_url or DEFAULT_BASE_URL
    email = email or DEFAULT_LOGIN_EMAIL
    password = password or DEFAULT_LOGIN_PASSWORD
    ol = OpenLibrary(base_url)
    try:
        ol.login(email, password)
        if ol.cookie:
            print(f"  Logged in as '{email}'.")
        else:
            print(f"  Warning: login returned no session cookie for '{email}'.")
            print("  Some features (imports, role changes) may not work.")
    except (OLError, requests.RequestException) as e:
        print(f"  Warning: login failed ({e}). Continuing without auth.")
    return ol


def infobase_save(docs, comment="shelfie"):
    """Save documents via infobase directly (bypasses web app save bugs)."""
    resp = requests.post(
        f"{DEFAULT_INFOBASE_URL}/save_many",
        data={"query": json.dumps(docs), "comment": comment},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def solr_request(path, base_url=None):
    """Make a request to the local Solr instance."""
    solr_url = (base_url or "http://solr:8983") + path
    try:
        resp = requests.get(solr_url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError, KeyError) as e:
        print(f"  Solr error: {e}")
        return None


def get_work_keys_from_solr(limit=1000):
    """Fetch available work keys from Solr."""
    data = solr_request(
        f"/solr/openlibrary/select?q=type:work&fl=key&rows={limit}&wt=json"
    )
    if data and "response" in data:
        return [doc["key"] for doc in data["response"]["docs"]]
    return []


def get_work_keys(ol, limit=500):
    """Get work keys from Solr, falling back to infobase query."""
    work_keys = get_work_keys_from_solr(limit=limit)
    if not work_keys:
        try:
            results = ol.query(type="/type/work", limit=limit)
            work_keys = [str(r) for r in results]
        except OLError:
            pass
    return work_keys


SEARCH_FIELDS = (
    "key,title,author_name,first_publish_year,publisher,"
    "subject,isbn,cover_i,number_of_pages_median"
)
COVERS_URL_TEMPLATE = "https://covers.openlibrary.org/b/id/{}-L.jpg"


REJECTED_PUBLISHERS = {
    "independently published",
    "independent publisher",
    "createspace independent publishing platform",
    "createspace",
    "unknown",
}

REJECTED_TITLE_WORDS = {"study guide", "workbook", "test bank", "solutions manual"}


def _is_low_quality(doc):
    """Check if a search doc is likely junk (study guides, self-published, etc.)."""
    title = doc.get("title", "").lower()
    if any(word in title for word in REJECTED_TITLE_WORDS):
        return True
    publishers = doc.get("publisher", [])
    return bool(publishers and all(p.casefold() in REJECTED_PUBLISHERS for p in publishers[:3]))


def _pick_publisher(doc):
    """Pick the first non-rejected publisher, or 'Unknown'."""
    for p in doc.get("publisher", []):
        if p.casefold() not in REJECTED_PUBLISHERS:
            return [p]
    return ["Unknown"]


def _search_doc_to_record(doc, source_tag):
    """Convert an openlibrary.org search API doc into an import record."""
    record = {
        "title": doc["title"],
        "authors": [{"name": a} for a in doc.get("author_name", ["Unknown"])],
        "publishers": _pick_publisher(doc),
        "publish_date": str(doc.get("first_publish_year", "2000")),
        "source_records": [source_tag],
        "subjects": doc.get("subject", [])[:10],
    }
    isbns = doc.get("isbn", [])
    if isbns:
        isbn = isbns[0]
        if len(isbn) == 13:
            record["isbn_13"] = [isbn]
        elif len(isbn) == 10:
            record["isbn_10"] = [isbn]
    cover_id = doc.get("cover_i")
    if cover_id:
        record["cover"] = COVERS_URL_TEMPLATE.format(cover_id)
    pages = doc.get("number_of_pages_median")
    if pages:
        record["number_of_pages"] = pages
    return record


def _import_and_get_work_key(ol, record):
    """Import a record and return the work key, or None on failure."""
    try:
        result = ol.import_data(json.dumps(record))
        result_data = json.loads(result) if isinstance(result, str) else result
        if result_data.get("success"):
            return result_data.get("work", {}).get("key")
    except (OLError, requests.RequestException, json.JSONDecodeError):
        pass
    return None


# ---------------------------------------------------------------------------
# Feature: Add Books
# ---------------------------------------------------------------------------


SEARCH_QUERIES = [
    "fiction", "science fiction", "fantasy", "mystery", "romance",
    "history", "biography", "philosophy", "poetry", "adventure",
    "horror", "thriller", "children", "young adult", "graphic novel",
    "cooking", "travel", "science", "mathematics", "art",
    "music", "psychology", "economics", "politics", "religion",
    "classic literature", "detective", "war", "nature", "technology",
]


def _fetch_books_from_prod(count):
    """Fetch real book data from openlibrary.org search API."""
    books = []
    seen_keys = set()

    queries = SEARCH_QUERIES.copy()
    random.shuffle(queries)

    for query in queries:
        if len(books) >= count:
            break
        offset = random.randint(0, 50)
        batch_size = min(count - len(books), 100)
        try:
            resp = requests.get(
                "https://openlibrary.org/search.json",
                params={"q": query, "limit": batch_size, "offset": offset, "fields": SEARCH_FIELDS},
                timeout=15,
            )
            resp.raise_for_status()
            docs = resp.json().get("docs", [])
        except (requests.RequestException, ValueError):
            continue

        for doc in docs:
            if len(books) >= count:
                break
            work_key = doc.get("key", "")
            if work_key in seen_keys or not doc.get("title") or _is_low_quality(doc):
                continue
            seen_keys.add(work_key)
            books.append(_search_doc_to_record(doc, f"shelfie:prod-{work_key}"))

    return books


def _import_books(ol, records):
    """Import a list of book records and print progress."""
    success = 0
    errors = 0
    total = len(records)

    for i, record in enumerate(records):
        try:
            result = ol.import_data(json.dumps(record))
            result_data = json.loads(result) if isinstance(result, str) else result
            if result_data.get("success"):
                success += 1
            else:
                errors += 1
                if errors <= 3:
                    print(f"  Failed: {record['title']} - {result_data.get('error_message', result_data)}")
        except (OLError, requests.RequestException, json.JSONDecodeError) as e:
            errors += 1
            if errors <= 3:
                print(f"  Error importing '{record['title']}': {e}")

        done = i + 1
        if done % 10 == 0 or done == total:
            print(f"  Progress: {done}/{total} (success={success}, errors={errors})")

    return success, errors


def cmd_add_books(ol, count=10, source="production"):
    """Import books — from openlibrary.org (default) or local seed data."""
    print_header("Add Books")

    if source == "production":
        print(f"  Fetching {count} books from openlibrary.org...")
        records = _fetch_books_from_prod(count)
        if not records:
            print("  Could not reach openlibrary.org. Falling back to seed data.")
            source = "seed"
        else:
            print(f"  Fetched {len(records)} unique books (with covers & subjects).")

    if source == "seed":
        books = load_json("books.json")
        total_available = len(books)
        print(f"  Using seed file ({total_available} books).")
        records = []
        for i in range(count):
            book = books[i % total_available]
            record = {
                "title": book["title"],
                "authors": book.get("authors", []),
                "publishers": book.get("publishers", []),
                "publish_date": book.get("publish_date", "2000"),
                "subjects": book.get("subjects", []),
                "source_records": [f"shelfie:seed-{i}"],
            }
            if book.get("number_of_pages"):
                record["number_of_pages"] = book["number_of_pages"]
            records.append(record)

    success, errors = _import_books(ol, records)

    print(f"\n  Done! {success} books imported, {errors} errors.")
    if success > 0:
        print("  Tip: Books may not appear in search until Solr reindexes.")
        print("  Use 'Manage Solr Index' or wait for solr-updater to catch up.")
    return success


# ---------------------------------------------------------------------------
# Feature: Change User Role
# ---------------------------------------------------------------------------


def cmd_set_role(ol, username=None, role=None, action="add"):
    """Add or remove a user from a usergroup."""
    print_header("Change User Role")

    if not username:
        username = ask("Enter username (e.g. openlibrary)", DEFAULT_USERNAME)

    user_key = f"/people/{username}"

    # Verify user exists
    try:
        user = ol.get(user_key)
        print(f"  Found user: {user.get('displayname', username)}")
    except OLError:
        print(f"  Error: user '{username}' not found.")
        return

    # Show current groups
    try:
        current_groups = []
        for group_name in USERGROUPS:
            try:
                group = ol.get(f"/usergroup/{group_name}")
                members = group.get("members", [])
                member_keys = [
                    m.get("key", m) if isinstance(m, dict) else str(m)
                    for m in members
                ]
                if user_key in member_keys:
                    current_groups.append(group_name)
            except OLError:
                pass
        if current_groups:
            print(f"  Current roles: {', '.join(current_groups)}")
        else:
            print("  Current roles: (none)")
    except (OLError, requests.RequestException) as e:
        print(f"  Could not fetch current roles: {e}")

    if not role:
        action_choice = choose("Action", ["Add role", "Remove role"])
        action = "add" if action_choice == "Add role" else "remove"
        role = choose("Select role", USERGROUPS)

    group_key = f"/usergroup/{role}"

    try:
        group = ol.get(group_key)
    except OLError:
        print(f"  Error: usergroup '{role}' not found.")
        return

    raw_members = group.get("members", [])
    # Normalize: Reference strings or dicts -> plain string keys
    member_keys = [str(m) if not isinstance(m, dict) else m.get("key", str(m)) for m in raw_members]

    if action == "add":
        if user_key in member_keys:
            print(f"  User '{username}' is already in '{role}'.")
            return
        member_keys.append(user_key)
    else:
        if user_key not in member_keys:
            print(f"  User '{username}' is not in '{role}'.")
            return
        member_keys = [k for k in member_keys if k != user_key]

    # Save via infobase (web app PUT has issues in local dev)
    doc = {
        "key": group_key,
        "type": {"key": "/type/usergroup"},
        "members": [{"key": k} for k in member_keys],
    }
    try:
        infobase_save([doc], comment=f"shelfie: {'adding' if action == 'add' else 'removing'} {username} {'to' if action == 'add' else 'from'} {role}")
        verb = "Added" if action == "add" else "Removed"
        prep = "to" if action == "add" else "from"
        print(f"  {verb} '{username}' {prep} '{role}'.")
    except requests.RequestException as e:
        print(f"  Error saving group: {e}")


# ---------------------------------------------------------------------------
# Feature: Generate Lists
# ---------------------------------------------------------------------------


PROD_LIST_USERS = [
    "mekBot", "openlibrary", "staffpicks", "internetarchive",
]


def _fetch_prod_lists(count):
    """Fetch real public lists from openlibrary.org."""
    fetched = []
    for user in PROD_LIST_USERS:
        if len(fetched) >= count:
            break
        try:
            resp = requests.get(
                f"https://openlibrary.org/people/{user}/lists.json",
                params={"limit": min(count - len(fetched), 20)},
                timeout=15,
            )
            resp.raise_for_status()
            entries = resp.json().get("entries", [])
        except (requests.RequestException, ValueError):
            continue

        for entry in entries:
            if len(fetched) >= count:
                break
            name = entry.get("name", "")
            seed_count = entry.get("seed_count", 0)
            if not name or seed_count < 3:
                continue

            # Fetch the seeds for this list
            list_url = entry.get("url", "")
            try:
                seeds_resp = requests.get(
                    f"https://openlibrary.org{list_url}/seeds.json",
                    params={"limit": 20},
                    timeout=15,
                )
                seeds_resp.raise_for_status()
                seed_entries = seeds_resp.json().get("entries", [])
            except (requests.RequestException, ValueError):
                continue

            # Extract work/edition keys and titles from seeds
            seed_keys = []
            seed_titles = {}
            for s in seed_entries:
                url = s.get("url", "")
                title = s.get("title", "")
                if url.startswith(("/works/", "/books/")):
                    seed_keys.append(url)
                    if title:
                        seed_titles[url] = title

            if len(seed_keys) >= 3:
                fetched.append({
                    "name": name,
                    "description": f"From {user}'s lists on openlibrary.org",
                    "seed_keys": seed_keys,
                    "_seed_titles": seed_titles,
                })

    return fetched


def _import_list_seeds(ol, prod_list):
    """Import seed works from a production list into local DB. Returns local work keys."""
    imported_keys = []
    for seed_key in prod_list["seed_keys"]:
        title = prod_list.get("_seed_titles", {}).get(seed_key)
        if not title:
            try:
                resp = requests.get(f"https://openlibrary.org{seed_key}.json", timeout=5)
                resp.raise_for_status()
                title = resp.json().get("title", "")
            except (requests.RequestException, ValueError):
                continue
        if not title:
            continue

        try:
            search_resp = requests.get(
                "https://openlibrary.org/search.json",
                params={"title": title, "limit": 1, "fields": SEARCH_FIELDS},
                timeout=10,
            )
            search_resp.raise_for_status()
            docs = search_resp.json().get("docs", [])
        except (requests.RequestException, ValueError):
            continue
        if not docs:
            continue

        record = _search_doc_to_record(docs[0], f"shelfie:list-{docs[0].get('key', '')}")
        work_key = _import_and_get_work_key(ol, record)
        if work_key:
            imported_keys.append(work_key)
    return imported_keys


def cmd_generate_lists(ol, count=1, username=None):
    """Create reading lists from real openlibrary.org lists."""
    print_header("Generate Lists")

    if not username:
        username = ask("Enter username for list owner", DEFAULT_USERNAME)

    print("  Fetching real lists from openlibrary.org...")
    prod_lists = _fetch_prod_lists(count)

    if not prod_lists:
        print("  Could not fetch lists from production. Using local works instead.")
        list_templates = load_json("list_names.json")
        work_keys = get_work_keys(ol)

        if not work_keys:
            print("  No works found. Add books first!")
            return

        for i in range(count):
            template = list_templates[i % len(list_templates)]
            num_seeds = min(random.randint(5, 20), len(work_keys))
            prod_lists.append({
                "name": template["name"],
                "description": template["description"],
                "seed_keys": random.sample(work_keys, num_seeds),
            })

    print(f"  Got {len(prod_lists)} lists. Importing seed works and creating lists...")

    success = 0
    for pl in prod_lists[:count]:
        imported_keys = _import_list_seeds(ol, pl)

        # Create the list locally with only successfully imported work keys
        seeds = [{"key": k} for k in imported_keys if k]
        if not seeds:
            print(f"  Skipping '{pl['name']}': no works could be imported")
            continue

        list_data = json.dumps({
            "name": pl["name"],
            "description": pl.get("description", ""),
            "seeds": seeds,
        })

        try:
            resp = ol._request(
                f"/people/{username}/lists.json",
                method="POST",
                data=list_data,
                headers={"Content-Type": "application/json"},
            )
            result = resp.json()
            list_key = result.get("key", "?")
            print(f"  Created: {pl['name']} ({list_key}) with {len(seeds)} seeds")
            success += 1
        except (OLError, requests.RequestException, json.JSONDecodeError) as e:
            print(f"  Error creating list '{pl['name']}': {e}")

    print(f"\n  Done! {success}/{count} lists created.")


# ---------------------------------------------------------------------------
# Feature: Populate Subjects
# ---------------------------------------------------------------------------


def cmd_populate_subjects(ol):
    """Find works missing subjects and assign them from keyword matching."""
    print_header("Populate Subjects")

    subject_data = load_json("subjects.json")
    keywords = subject_data["keywords"]
    fallback = subject_data["fallback"]

    # Find works without subjects
    try:
        all_works = ol.query(type="/type/work", limit=500)
    except OLError as e:
        print(f"  Error querying works: {e}")
        return

    if not all_works:
        print("  No works found. Add books first!")
        return

    print(f"  Checking {len(all_works)} works for missing subjects...")

    updated = 0
    skipped = 0
    errors = 0
    # ol.query returns Reference strings like "/works/OL1W", not dicts
    for work_ref in all_works:
        work_key = str(work_ref)
        try:
            work = ol.get(work_key)
        except OLError:
            continue

        existing_subjects = work.get("subjects", [])
        if existing_subjects:
            skipped += 1
            continue

        # Match subjects based on title keywords
        title = work.get("title", "").lower()
        matched_subjects = set()
        for keyword, subjects in keywords.items():
            if keyword in title:
                matched_subjects.update(subjects)

        if not matched_subjects:
            matched_subjects = set(fallback)

        # Save via infobase
        doc = {
            "key": work_key,
            "type": {"key": "/type/work"},
            "subjects": list(matched_subjects),
        }
        try:
            infobase_save([doc], comment="shelfie: adding subjects")
            updated += 1
        except requests.RequestException as e:
            errors += 1
            if errors <= 3:
                print(f"  Error updating {work_key}: {e}")

    print(f"\n  Done! {updated} works updated, {skipped} already had subjects.")


# ---------------------------------------------------------------------------
# Feature: Stats
# ---------------------------------------------------------------------------


def _infobase_count(doc_type):
    """Count documents of a given type in infobase."""
    try:
        resp = requests.get(
            f"{DEFAULT_INFOBASE_URL}/things",
            params={"query": json.dumps({"type": doc_type, "limit": 10000})},
            timeout=10,
        )
        resp.raise_for_status()
        return len(resp.json())
    except (requests.RequestException, ValueError):
        return "?"


def _solr_count(query="*:*"):
    """Count documents matching a Solr query."""
    data = solr_request(f"/solr/openlibrary/select?q={query}&rows=0&wt=json")
    if data:
        return data.get("response", {}).get("numFound", "?")
    return "?"


def _solr_facet_count(field):
    """Count unique values of a facet field in Solr."""
    data = solr_request(
        f"/solr/openlibrary/select?q=type:work&rows=0&facet=true"
        f"&facet.field={field}&facet.limit=-1&wt=json"
    )
    if data:
        facets = data.get("facet_counts", {}).get("facet_fields", {}).get(field, [])
        return len(facets) // 2  # facets alternate value/count
    return "?"


def cmd_stats(ol):
    """Show database statistics."""
    print_header("Database Stats")

    print("  Fetching counts...\n")

    # Database counts (infobase)
    db_counts = {
        "Works": _infobase_count("/type/work"),
        "Editions": _infobase_count("/type/edition"),
        "Authors": _infobase_count("/type/author"),
        "Users": _infobase_count("/type/user"),
        "Lists": _infobase_count("/type/list"),
        "Series": _infobase_count("/type/series"),
        "Usergroups": _infobase_count("/type/usergroup"),
    }

    print("  Database (infobase)")
    print("  " + "-" * 30)
    for label, count in db_counts.items():
        print(f"    {label:<20} {count:>6}")

    # Solr counts
    print()
    print("  Search Index (Solr)")
    print("  " + "-" * 30)
    solr_counts = {
        "Works": _solr_count("type:work"),
        "Editions": _solr_count("type:edition"),
        "Authors": _solr_count("type:author"),
        "Total docs": _solr_count("*:*"),
    }
    for label, count in solr_counts.items():
        print(f"    {label:<20} {count:>6}")

    # Coverage stats
    print()
    print("  Coverage")
    print("  " + "-" * 30)
    works_with_covers = _solr_count("type:work AND cover_i:[* TO *]")
    works_with_subjects = _solr_count("type:work AND subject:[* TO *]")
    total_works = solr_counts.get("Works", 0)

    print(f"    {'Works with covers':<20} {works_with_covers:>6}", end="")
    if isinstance(works_with_covers, int) and isinstance(total_works, int) and total_works > 0:
        print(f"  ({works_with_covers * 100 // total_works}%)")
    else:
        print()

    print(f"    {'Works with subjects':<20} {works_with_subjects:>6}", end="")
    if isinstance(works_with_subjects, int) and isinstance(total_works, int) and total_works > 0:
        print(f"  ({works_with_subjects * 100 // total_works}%)")
    else:
        print()

    unique_subjects = _solr_facet_count("subject")
    print(f"    {'Unique subjects':<20} {unique_subjects:>6}")

    # Sync status
    print()
    print("  Sync Status")
    print("  " + "-" * 30)
    db_works = db_counts.get("Works", "?")
    solr_works = solr_counts.get("Works", "?")
    if isinstance(db_works, int) and isinstance(solr_works, int):
        unindexed = db_works - solr_works
        if unindexed > 0:
            print(f"    {unindexed} works not yet indexed in Solr")
        elif unindexed == 0:
            print("    All works indexed in Solr")
        else:
            print(f"    Solr has {-unindexed} more works than DB (stale entries)")
    else:
        print("    Could not compare DB and Solr counts")


# ---------------------------------------------------------------------------
# Feature: Manage Solr Index
# ---------------------------------------------------------------------------


def cmd_manage_solr(ol):
    """Manage the local Solr search index."""
    print_header("Manage Solr Index")

    options = [
        "Check index status",
        "Reindex specific works",
        "Back to menu",
    ]
    choice = choose("Choose action", options)

    if choice == "Check index status":
        data = solr_request("/solr/openlibrary/select?q=*:*&rows=0&wt=json")
        if data:
            num_docs = data.get("response", {}).get("numFound", "?")
            print(f"  Total documents in Solr: {num_docs}")

            # Break down by type
            for doc_type in ["work", "author", "edition"]:
                type_data = solr_request(
                    f"/solr/openlibrary/select?q=type:{doc_type}&rows=0&wt=json"
                )
                if type_data:
                    n = type_data.get("response", {}).get("numFound", "?")
                    print(f"    {doc_type}s: {n}")
        else:
            print("  Could not connect to Solr at solr:8983")

    elif choice == "Reindex specific works":
        raw = ask("Enter work keys (comma-separated, e.g. /works/OL1W,/works/OL2W)")
        if not raw:
            return
        keys = [k.strip() for k in raw.split(",") if k.strip()]
        for key in keys:
            try:
                ol._request(
                    f"/admin/solr/update?key={key}",
                    method="GET",
                )
                print(f"  Reindex requested for {key}")
            except OLError as e:
                print(f"  Error reindexing {key}: {e}")


# ---------------------------------------------------------------------------
# Feature: Create Test Accounts
# ---------------------------------------------------------------------------


def cmd_create_accounts(ol, count=5, prefix="testuser", password=None, interactive=True):
    """Create test user accounts with known passwords."""
    print_header("Create Test Accounts")

    if count <= 0:
        count = int(ask("How many accounts?", "5"))
    if not prefix:
        prefix = ask("Username prefix", "testuser")

    if not password:
        password = ask("Password for all accounts", "password123") if interactive else "password123"

    success = 0
    for i in range(1, count + 1):
        username = f"{prefix}_{i}"
        email = f"{username}@example.com"

        data = json.dumps({
            "username": username,
            "email": email,
            "password": password,
            "displayname": f"Test User {i}",
        })

        try:
            ol._request(
                "/account/create",
                method="POST",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            print(f"  Created: {username} ({email})")
            success += 1
        except OLError as e:
            if "already" in str(e).lower() or "registered" in str(e).lower():
                print(f"  Skipped: {username} (already exists)")
                success += 1  # Count existing as success
            else:
                print(f"  Error creating {username}: {e}")

    print(f"\n  Done! {success}/{count} accounts ready.")
    print(f"  Login with: username='{prefix}_N', password='{password}'")

    if interactive and success > 0 and confirm("  Assign a role to all created accounts?"):
        role = choose("Select role", USERGROUPS)
        group_key = f"/usergroup/{role}"
        try:
            group = ol.get(group_key)
            raw_members = group.get("members", [])
            member_keys = {str(m) if not isinstance(m, dict) else m.get("key", str(m)) for m in raw_members}
            for i in range(1, count + 1):
                member_keys.add(f"/people/{prefix}_{i}")
            doc = {
                "key": group_key,
                "type": {"key": "/type/usergroup"},
                "members": [{"key": k} for k in member_keys],
            }
            infobase_save([doc], comment=f"shelfie: adding {count} accounts to {role}")
            print(f"  Added all accounts to '{role}'.")
        except (OLError, requests.RequestException) as e:
            print(f"  Error assigning role: {e}")


# ---------------------------------------------------------------------------
# Feature: Seed Reviews/Ratings
# ---------------------------------------------------------------------------


def cmd_seed_ratings(ol, count=10, username=None):
    """Add ratings to existing books."""
    print_header("Seed Reviews & Ratings")

    work_keys = get_work_keys(ol, limit=200)

    if not work_keys:
        print("  No works found. Add books first!")
        return

    if not username:
        username = ask("Username to rate as", DEFAULT_USERNAME)
    print(f"  Will add {count} ratings as '{username}' across {len(work_keys)} works.")

    success = 0
    selected_works = random.choices(work_keys, k=min(count, len(work_keys)))

    for work_key in selected_works:
        rating = random.randint(1, 5)
        work_id = work_key.split("/")[-1]

        try:
            data = json.dumps({
                "rating": rating,
                "edition_key": "",
            })
            ol._request(
                f"/works/{work_id}/ratings.json",
                method="POST",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            print(f"  Rated {work_key}: {'*' * rating}")
            success += 1
        except (OLError, requests.RequestException, json.JSONDecodeError) as e:
            print(f"  Error rating {work_key}: {e}")

    print(f"\n  Done! {success}/{len(selected_works)} ratings added.")


# ---------------------------------------------------------------------------
# Feature: Seed Reading Logs
# ---------------------------------------------------------------------------


def cmd_seed_reading_log(ol, count=20, username=None):
    """Add books to a user's reading shelves."""
    print_header("Seed Reading Log")

    if not username:
        username = ask("Username", DEFAULT_USERNAME)

    work_keys = get_work_keys(ol, limit=500)

    if not work_keys:
        print("  No works found. Add books first!")
        return

    available = min(count, len(work_keys))
    selected = random.sample(work_keys, available)
    print(f"  Adding {available} books to reading shelves for '{username}'...")

    success = 0
    for i, work_key in enumerate(selected):
        r = random.random()
        if r < 0.3:
            shelf_id = 1
        elif r < 0.5:
            shelf_id = 2
        else:
            shelf_id = 3

        # Extract work ID (e.g., /works/OL123W -> OL123W)
        work_id = work_key.split("/")[-1]

        try:
            ol._request(
                f"/works/{work_id}/bookshelves.json",
                method="POST",
                params={"bookshelf_id": str(shelf_id), "action": "add"},
            )
            success += 1
        except (OLError, requests.RequestException) as e:
            if success == 0:
                print(f"  Error: {e}")
                return

        done = i + 1
        if done % 10 == 0 or done == available:
            print(f"  Progress: {done}/{available}")

    # Show distribution
    print(f"\n  Done! {success} books added to reading log.")
    print("  Distributed across: Want to Read, Currently Reading, Already Read")


# ---------------------------------------------------------------------------
# Feature: Seed Series
# ---------------------------------------------------------------------------


REAL_SERIES = [
    {
        "name": "Harry Potter",
        "description": "Fantasy series by J.K. Rowling following a young wizard",
        "query": "harry potter rowling",
        "titles": [
            "Harry Potter and the Philosopher's Stone",
            "Harry Potter and the Chamber of Secrets",
            "Harry Potter and the Prisoner of Azkaban",
            "Harry Potter and the Goblet of Fire",
            "Harry Potter and the Order of the Phoenix",
            "Harry Potter and the Half-Blood Prince",
            "Harry Potter and the Deathly Hallows",
        ],
    },
    {
        "name": "The Lord of the Rings",
        "description": "Epic fantasy trilogy by J.R.R. Tolkien",
        "query": "lord of the rings tolkien",
        "titles": [
            "The Fellowship of the Ring",
            "The Two Towers",
            "The Return of the King",
        ],
    },
    {
        "name": "A Song of Ice and Fire",
        "description": "Epic fantasy series by George R.R. Martin",
        "query": "song of ice and fire martin",
        "titles": [
            "A Game of Thrones",
            "A Clash of Kings",
            "A Storm of Swords",
            "A Feast for Crows",
            "A Dance with Dragons",
        ],
    },
    {
        "name": "The Hunger Games",
        "description": "Dystopian series by Suzanne Collins",
        "query": "hunger games collins",
        "titles": [
            "The Hunger Games",
            "Catching Fire",
            "Mockingjay",
        ],
    },
    {
        "name": "Foundation",
        "description": "Science fiction series by Isaac Asimov",
        "query": "foundation asimov",
        "titles": [
            "Foundation",
            "Foundation and Empire",
            "Second Foundation",
        ],
    },
    {
        "name": "Dune",
        "description": "Science fiction series by Frank Herbert",
        "query": "dune herbert",
        "titles": [
            "Dune",
            "Dune Messiah",
            "Children of Dune",
            "God Emperor of Dune",
        ],
    },
    {
        "name": "The Chronicles of Narnia",
        "description": "Fantasy series by C.S. Lewis",
        "query": "narnia lewis",
        "titles": [
            "The Lion, the Witch and the Wardrobe",
            "Prince Caspian",
            "The Voyage of the Dawn Treader",
            "The Silver Chair",
            "The Horse and His Boy",
            "The Magician's Nephew",
            "The Last Battle",
        ],
    },
    {
        "name": "Discworld",
        "description": "Comic fantasy series by Terry Pratchett",
        "query": "discworld pratchett",
        "titles": [
            "The Colour of Magic",
            "The Light Fantastic",
            "Equal Rites",
            "Mort",
            "Guards! Guards!",
            "Small Gods",
        ],
    },
]


def _fetch_series_works(series_def):
    """Fetch real works for a series from openlibrary.org search."""
    try:
        resp = requests.get(
            "https://openlibrary.org/search.json",
            params={"q": series_def["query"], "limit": 50, "fields": SEARCH_FIELDS},
            timeout=15,
        )
        resp.raise_for_status()
        docs = resp.json().get("docs", [])
    except (requests.RequestException, ValueError):
        return []

    # Match search results to the expected title order
    ordered = []
    for expected_title in series_def["titles"]:
        expected_lower = expected_title.lower()
        best = None
        for doc in docs:
            doc_title = doc.get("title", "").lower()
            if expected_lower in doc_title or doc_title in expected_lower:
                best = doc
                break
        if best:
            ordered.append(best)
            docs.remove(best)

    return ordered


def cmd_seed_series(ol, count=3):
    """Create real book series from openlibrary.org."""
    print_header("Seed Series")

    print("  Fetching real series data from openlibrary.org...")

    # Find the next available series key
    try:
        resp = requests.get(
            f"{DEFAULT_INFOBASE_URL}/things",
            params={"query": json.dumps({"type": "/type/series", "limit": 10000})},
            timeout=10,
        )
        existing = resp.json()
        max_id = 0
        for key in existing:
            if key.startswith("/series/OL") and key.endswith("L"):
                with contextlib.suppress(ValueError):
                    max_id = max(max_id, int(key[10:-1]))
    except (requests.RequestException, ValueError):
        max_id = 100

    series_pool = REAL_SERIES.copy()
    random.shuffle(series_pool)

    success = 0
    for i in range(min(count, len(series_pool))):
        series_def = series_pool[i]
        series_name = series_def["name"]

        works = _fetch_series_works(series_def)
        if len(works) < 2:
            print(f"  Skipping '{series_name}': not enough works found online")
            continue

        imported_work_keys = []
        for doc in works:
            record = _search_doc_to_record(doc, f"shelfie:series-{doc.get('key', '')}")
            work_key = _import_and_get_work_key(ol, record)
            if work_key:
                imported_work_keys.append(work_key)

        if len(imported_work_keys) < 2:
            print(f"  Skipping '{series_name}': could not import enough works")
            continue

        # Create the series and link works
        series_key = f"/series/OL{max_id + success + 1}L"
        series_doc = {
            "key": series_key,
            "type": {"key": "/type/series"},
            "name": series_name,
            "description": series_def["description"],
        }

        try:
            infobase_save([series_doc], comment=f"shelfie: creating series '{series_name}'")
        except requests.RequestException as e:
            print(f"  Error creating series '{series_name}': {e}")
            continue

        work_docs = [
            {
                "key": wk,
                "type": {"key": "/type/work"},
                "series": [{"series": {"key": series_key}, "position": str(pos + 1)}],
            }
            for pos, wk in enumerate(imported_work_keys)
        ]
        with contextlib.suppress(requests.RequestException):
            infobase_save(work_docs, comment=f"shelfie: linking works to series '{series_name}'")

        print(f"  Created: {series_name} ({series_key}) with {len(imported_work_keys)} works")
        titles = [w["title"] for w in works[:len(imported_work_keys)]]
        for pos, title in enumerate(titles, 1):
            print(f"    {pos}. {title}")
        success += 1

    print(f"\n  Done! {success}/{count} series created.")


# ---------------------------------------------------------------------------
# Feature: Populate Everything (batch)
# ---------------------------------------------------------------------------


def cmd_populate_all(ol):
    """Run all seeding operations to get a rich local dev database."""
    print_header("Populate Everything")
    print("  This will seed your local DB with a rich set of test data:")
    print("    - 100 books from openlibrary.org (with covers)")
    print("    - Subjects on all works")
    print("    - 5 reading lists")
    print("    - 30 ratings")
    print("    - 20 books on reading shelves")
    print("    - 3 series with ordered works")
    print()

    if not confirm("  Proceed?"):
        print("  Cancelled.")
        return

    print()
    cmd_add_books(ol, count=100, source="production")
    print()
    cmd_populate_subjects(ol)
    print()
    cmd_generate_lists(ol, count=5, username=DEFAULT_USERNAME)
    print()
    cmd_seed_ratings(ol, count=30, username=DEFAULT_USERNAME)
    print()
    cmd_seed_reading_log(ol, count=20, username=DEFAULT_USERNAME)
    print()
    cmd_seed_series(ol, count=3)

    print()
    print_header("All Done!")
    print("  Your local DB is now populated with rich test data.")
    print("  Run 'Stats' to see the current state.")


# ---------------------------------------------------------------------------
# Feature: Reset Local State
# ---------------------------------------------------------------------------


def cmd_reset_state(ol):
    """Clear books, lists, and test users from local database."""
    print_header("Reset Local State")
    print("  WARNING: This will delete data from your local dev database.")
    print("  This does NOT affect production.")
    print()

    options = [
        "Delete all imported books (source_records starting with 'shelfie:')",
        "Delete all test accounts (testuser_* pattern)",
        "Cancel",
    ]
    choice = choose("What to reset?", options)

    if choice == options[2]:
        print("  Cancelled.")
        return

    if choice == options[0]:
        if not confirm("  Really delete all shelfie-imported books?"):
            return
        # Find editions with shelfie source records
        try:
            editions = ol.query(
                type="/type/edition",
                source_records="shelfie:*",
                limit=False,
            )
            edition_list = list(editions) if hasattr(editions, '__next__') else editions
            if not edition_list:
                print("  No shelfie-imported books found.")
                return
            print(f"  Found {len(edition_list)} editions to remove...")
            # We can't truly delete in OL, but we can mark them
            # For local dev, direct DB cleanup is more practical
            print("  Note: Open Library doesn't support hard deletes.")
            print("  For a clean reset, rebuild the Docker volumes:")
            print("    docker compose down -v && docker compose up")
        except OLError as e:
            print(f"  Error: {e}")

    elif choice == options[1]:
        print("  Note: Account deletion is best done by rebuilding Docker volumes.")
        print("    docker compose down -v && docker compose up")


# ---------------------------------------------------------------------------
# Interactive Menu
# ---------------------------------------------------------------------------


MENU_OPTIONS = [
    "Populate everything",
    "Add books",
    "Generate lists",
    "Seed reading log",
    "Seed series",
    "Seed reviews & ratings",
    "Populate subjects on existing books",
    "Change user role",
    "Create test accounts",
    "Manage Solr index",
    "Stats",
    "Reset local state",
    "Exit",
]


BOLD = "\033[1m"
RESET = "\033[0m"
LOGO = f"""
{BOLD}   ____  _          _  __ _
  / ___|| |__   ___| |/ _(_) ___
  \\___ \\| '_ \\ / _ \\ | |_| |/ _ \\
   ___) | | | |  __/ |  _| |  __/
  |____/|_| |_|\\___|_|_| |_|\\___|
{RESET}
  Open Library Dev Tool
"""


DIM = "\033[2m"


def _print_startup_stats():
    """Print a compact stats summary below the logo."""
    works = _infobase_count("/type/work")
    editions = _infobase_count("/type/edition")
    authors = _infobase_count("/type/author")
    lists = _infobase_count("/type/list")
    series = _infobase_count("/type/series")
    users = _infobase_count("/type/user")
    covers = _solr_count("type:work AND cover_i:[* TO *]")
    subjects = _solr_facet_count("subject")

    def fmt(n):
        return str(n) if isinstance(n, int) else "?"

    print(f"  {DIM}works: {fmt(works)}  editions: {fmt(editions)}  authors: {fmt(authors)}  "
          f"covers: {fmt(covers)}")
    print(f"  lists: {fmt(lists)}  series: {fmt(series)}  subjects: {fmt(subjects)}  "
          f"users: {fmt(users)}{RESET}")


def interactive_menu():
    """Main interactive menu loop."""
    print(LOGO)
    print(f"  Server: {DEFAULT_BASE_URL}")
    _print_startup_stats()
    print()

    ol = connect()

    while True:
        try:
            print()
            choice = choose("Choose an option", MENU_OPTIONS)

            if choice == "Exit":
                print("  Bye!")
                break
            elif choice == "Populate everything":
                cmd_populate_all(ol)
            elif choice == "Add books":
                count_choice = choose("How many books?", ["10", "100", "1000"])
                source_choice = choose("Source?", ["Production (openlibrary.org)", "Seed data (offline)"])
                source = "production" if "Production" in source_choice else "seed"
                cmd_add_books(ol, count=int(count_choice), source=source)
            elif choice == "Generate lists":
                count_choice = choose("How many lists?", ["1", "5", "10"])
                cmd_generate_lists(ol, count=int(count_choice))
            elif choice == "Seed reading log":
                count_choice = choose("How many books to shelve?", ["10", "20", "50"])
                cmd_seed_reading_log(ol, count=int(count_choice))
            elif choice == "Seed series":
                count_choice = choose("How many series?", ["1", "3", "5"])
                cmd_seed_series(ol, count=int(count_choice))
            elif choice == "Seed reviews & ratings":
                count_choice = choose("How many ratings?", ["10", "50", "100"])
                cmd_seed_ratings(ol, count=int(count_choice))
            elif choice == "Populate subjects on existing books":
                cmd_populate_subjects(ol)
            elif choice == "Change user role":
                cmd_set_role(ol)
            elif choice == "Create test accounts":
                count_choice = choose("How many accounts?", ["1", "5", "10"])
                cmd_create_accounts(ol, count=int(count_choice))
            elif choice == "Manage Solr index":
                cmd_manage_solr(ol)
            elif choice == "Stats":
                cmd_stats(ol)
            elif choice == "Reset local state":
                cmd_reset_state(ol)
        except UserExit:
            print("\n  Bye!")
            break


# ---------------------------------------------------------------------------
# CLI Subcommands (non-interactive)
# ---------------------------------------------------------------------------


def build_parser():
    parser = argparse.ArgumentParser(
        prog="shelfie",
        description="Open Library development helper tool",
    )
    parser.add_argument(
        "--url", default=DEFAULT_BASE_URL, help="OL server URL"
    )
    parser.add_argument(
        "--email", default=DEFAULT_LOGIN_EMAIL, help="Login email"
    )
    parser.add_argument(
        "--password", default=DEFAULT_LOGIN_PASSWORD, help="Login password"
    )
    sub = parser.add_subparsers(dest="command")

    # add-books
    p = sub.add_parser("add-books", help="Import books into local dev")
    p.add_argument("--count", type=int, default=10)
    p.add_argument("--source", default="production", choices=["production", "seed"],
                   help="'production' fetches from openlibrary.org (default), 'seed' uses offline data")

    # set-role
    p = sub.add_parser("set-role", help="Change a user's role")
    p.add_argument("--username", required=True)
    p.add_argument("--role", required=True, choices=USERGROUPS)
    p.add_argument(
        "--action", default="add", choices=["add", "remove"]
    )

    # generate-lists
    p = sub.add_parser("generate-lists", help="Create reading lists")
    p.add_argument("--count", type=int, default=1)
    p.add_argument("--username", default=None)

    # populate-subjects
    sub.add_parser("populate-subjects", help="Add subjects to works missing them")

    # stats
    sub.add_parser("stats", help="Show database statistics")

    # manage-solr
    sub.add_parser("manage-solr", help="Check Solr index status")

    # create-accounts
    p = sub.add_parser("create-accounts", help="Create test user accounts")
    p.add_argument("--count", type=int, default=5)
    p.add_argument("--prefix", default="testuser")

    # seed-ratings
    p = sub.add_parser("seed-ratings", help="Add ratings to existing books")
    p.add_argument("--count", type=int, default=10)
    p.add_argument("--username", default=DEFAULT_USERNAME)

    # seed-reading-log
    p = sub.add_parser("seed-reading-log", help="Add books to reading shelves")
    p.add_argument("--count", type=int, default=20)
    p.add_argument("--username", default=DEFAULT_USERNAME)

    # seed-series
    p = sub.add_parser("seed-series", help="Create series with ordered works")
    p.add_argument("--count", type=int, default=3)

    # populate-all
    sub.add_parser("populate-all", help="Seed everything for a rich local DB")

    # reset
    sub.add_parser("reset", help="Reset local dev data")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    # No subcommand = interactive mode
    if not args.command:
        interactive_menu()
        return

    ol = connect(args.url, args.email, args.password)

    if args.command == "add-books":
        cmd_add_books(ol, count=args.count, source=args.source)
    elif args.command == "set-role":
        cmd_set_role(ol, username=args.username, role=args.role, action=args.action)
    elif args.command == "generate-lists":
        cmd_generate_lists(ol, count=args.count, username=args.username)
    elif args.command == "populate-subjects":
        cmd_populate_subjects(ol)
    elif args.command == "stats":
        cmd_stats(ol)
    elif args.command == "manage-solr":
        cmd_manage_solr(ol)
    elif args.command == "create-accounts":
        cmd_create_accounts(ol, count=args.count, prefix=args.prefix, interactive=False)
    elif args.command == "seed-ratings":
        cmd_seed_ratings(ol, count=args.count, username=args.username)
    elif args.command == "seed-reading-log":
        cmd_seed_reading_log(ol, count=args.count, username=args.username)
    elif args.command == "seed-series":
        cmd_seed_series(ol, count=args.count)
    elif args.command == "populate-all":
        cmd_populate_all(ol)
    elif args.command == "reset":
        cmd_reset_state(ol)



if __name__ == "__main__":
    main()
