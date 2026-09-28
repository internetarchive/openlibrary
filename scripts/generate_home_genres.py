#!/usr/bin/env python
"""Build openlibrary/plugins/openlibrary/home_genres.json, the genre → subgenre tree behind the
home page's "Browse the stacks" section (#13158).

The vocabulary comes from https://github.com/Open-Book-Genome-Project/tags. Works aren't tagged
with it yet (no Solr field, see #13151), so each term is resolved to the legacy `subject_key`
facet and queried as a prefix (`subject_key:science_fiction*`). Counts are fetched live from
production so thin shelves can be hidden at render time.

Usage:
    python scripts/generate_home_genres.py
    python scripts/generate_home_genres.py --tags-repo ~/Projects/tags   # local checkout
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

TAGS_REPO_RAW_BASE = "https://raw.githubusercontent.com/Open-Book-Genome-Project/tags/main"
OL_SEARCH_URL = "https://openlibrary.org/search.json"
DEFAULT_OUTPUT = Path("openlibrary/plugins/openlibrary/home_genres.json")

# Not shown on the home page.
EXCLUDED_GENRES = {"Erotica"}

# Subjects shelved alongside the genres, so nonfiction and kids' books have a way in too. These
# aren't in the genres vocabulary; `page` is the subject page the shelf links out to. Names are
# translated at render time (home.py SUBJECT_LABELS), so keep them in sync.
SUBJECTS = [
    ("Kids", "kids", "(juvenile_fiction OR juvenile_literature OR children's_fiction OR juvenile_nonfiction)", "/subjects/juvenile_fiction"),
    ("History", "history", "history", "/subjects/history"),
    ("Biography", "biography", "(biography OR biographies)", "/subjects/biography"),
    ("Philosophy", "philosophy", "philosophy", "/subjects/philosophy"),
    ("Psychology", "psychology", "psychology", "/subjects/psychology"),
    ("Poetry", "poetry", "poetry", "/subjects/poetry"),
    ("Travel", "travel", "travel", "/subjects/travel"),
    ("Science", "science", "science", "/subjects/science"),
    ("Cooking", "cooking", "(cooking OR cookery OR recipes)", "/subjects/cooking"),
    ("Religion", "religion", "religion", "/subjects/religion"),
    ("Art", "art", "art", "/subjects/art"),
    ("Textbooks", "textbooks", "textbooks", "/subjects/textbooks"),
]

# Vocabulary terms whose common cataloguing name differs from the tag name.
KNOWN_SYNONYMS = {
    "Sci-Fi": "science fiction",
    "Cli-fi": "climate fiction",
}

# Terms whose bare prefix drags in unrelated subjects (psychological* is mostly
# "psychological aspects", cult* is "culture", western* is "western civilization").
# Values are subject_key clauses, checked live against production.
QUERY_OVERRIDES = {
    "Action": "(action_and_adventure_fiction OR action_and_adventure OR action)",
    "Crime": "(crime OR crime_fiction OR crime_fiction_fiction)",
    "Cult": "cult",
    "Drama": "drama",
    "Epic": "(epic OR epic_fiction OR epic_fantasy OR epic_literature)",
    "Gothic": "gothic_fiction*",
    "Historical": "historical_fiction*",
    "Literary": "literary_fiction*",
    "Psychological": "psychological_fiction*",
    "Western": "(western_stories OR westerns OR western_fiction OR western)",
}

# Same normalization Solr indexing applies to a subject string (work.py: subject_name_to_key).
_RE_SUBJECT = re.compile("[, _]+")


def ol_subject_key(name: str) -> str:
    return _RE_SUBJECT.sub("_", name.lower()).strip("_")


def load_vocabulary(tag_type: str, tags_repo: Path | None) -> list[dict]:
    if tags_repo:
        data = json.loads((tags_repo / "tag_types" / tag_type / "vocabulary.json").read_text())
    else:
        with urllib.request.urlopen(f"{TAGS_REPO_RAW_BASE}/tag_types/{tag_type}/vocabulary.json", timeout=15) as resp:
            data = json.loads(resp.read())
    return data["tags"]


_count_cache: dict[str, int] = {}


def fetch_count(q: str) -> int:
    if q in _count_cache:
        return _count_cache[q]
    url = f"{OL_SEARCH_URL}?{urllib.parse.urlencode({'q': q, 'limit': 0})}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            count = json.loads(resp.read())["numFound"]
    except (urllib.error.URLError, TimeoutError, KeyError) as e:
        print(f"  warn: count lookup failed for {q!r} ({e}); using 0", file=sys.stderr)
        count = 0
    _count_cache[q] = count
    time.sleep(0.1)
    return count


def resolve_subject_key(tag: dict) -> tuple[str, int]:
    """Pick the best-populated subject_key for a vocabulary entry. The vocabulary's slug keeps
    hyphens ("true-crime") where Solr keys use underscores, and some terms are catalogued under
    a synonym, so each candidate is checked live and the biggest wins."""
    candidates = dict.fromkeys(
        c
        for c in [
            ol_subject_key(KNOWN_SYNONYMS[tag["tag"]]) if tag["tag"] in KNOWN_SYNONYMS else None,
            ol_subject_key(tag["tag"]),
            tag["slug"],
            tag["slug"].replace("-", "_"),
        ]
        if c
    )
    best_slug, best_count = tag["slug"], -1
    for slug in candidates:
        if (count := fetch_count(f"subject_key:{slug}*")) > best_count:
            best_slug, best_count = slug, count
    if best_slug != tag["slug"]:
        print(f"  {tag['tag']!r}: {tag['slug']!r} -> {best_slug!r} ({best_count})", file=sys.stderr)
    return best_slug, best_count


def node(tag: dict) -> dict:
    """`query` is the subject_key clause the home page searches with."""
    if tag["tag"] in QUERY_OVERRIDES:
        query = QUERY_OVERRIDES[tag["tag"]]
        work_count = fetch_count(f"subject_key:{query}")
    else:
        subject_key, work_count = resolve_subject_key(tag)
        query = f"{subject_key}*"
    return {
        "name": tag["tag"],
        "slug": tag["slug"],
        "tag_key": tag.get("key"),
        "query": query,
        "work_count": work_count,
        "readable_count": fetch_count(f"subject_key:{query} has_fulltext:true"),
    }


def build_subjects() -> list[dict]:
    return [
        {
            "name": name,
            "slug": slug,
            "query": query,
            "page": page,
            "work_count": fetch_count(f"subject_key:{query}"),
            "readable_count": fetch_count(f"subject_key:{query} has_fulltext:true"),
            "subgenres": [],
        }
        for name, slug, query, page in SUBJECTS
    ]


def build(genres: list[dict], subgenres: list[dict]) -> list[dict]:
    tree = {g["tag"]: {**node(g), "subgenres": []} for g in genres if g["tag"] not in EXCLUDED_GENRES}
    for sg in subgenres:
        sg_node = node(sg)
        for parent in sg.get("parent_genres", []):
            if parent in tree:
                tree[parent]["subgenres"].append(sg_node)
    for g in tree.values():
        g["subgenres"].sort(key=lambda s: -s["readable_count"])
    return sorted(tree.values(), key=lambda g: g["name"])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tags-repo", type=Path, help="Local Open-Book-Genome-Project/tags checkout; fetched from GitHub when omitted.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    genres = load_vocabulary("genres", args.tags_repo)
    subgenres = load_vocabulary("subgenres", args.tags_repo)
    print(f"{len(genres)} genres, {len(subgenres)} subgenres; fetching counts from {OL_SEARCH_URL}", file=sys.stderr)
    out = {
        "generated": datetime.now(UTC).strftime("%Y-%m-%d"),
        "source": f"{TAGS_REPO_RAW_BASE}/tag_types/",
        "genres": build(genres, subgenres),
        "subjects": build_subjects(),
    }
    args.output.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
