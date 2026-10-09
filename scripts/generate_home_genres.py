#!/usr/bin/env python
"""Build openlibrary/plugins/openlibrary/home_genres.json, the genre → subgenre trees behind the
home page's "Browse the stacks" (#13158).

The file is a list of genre-explorer ClassificationNode trees (#13208). Top-level nodes are the
home page's categories: Lokesh's genres (#13783), then the nonfiction/kids "subject" tiles. The
genres reuse the Genre Explorer's subgenre trees (openlibrary/components/LibraryExplorer/genre.json)
as-is; the subject tiles aren't in that vocabulary, so their subgenres are curated below. Each
node's `count` is its readable (borrowable or public) book total, fetched live from production so
thin shelves can be dropped.

Once #13208 lands, both pages should share one generator.

Usage:
    python scripts/generate_home_genres.py --genre-json openlibrary/components/LibraryExplorer/genre.json
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OL_SEARCH_URL = "https://openlibrary.org/search.json"
DEFAULT_OUTPUT = Path("openlibrary/plugins/openlibrary/home_genres.json")
DEFAULT_GENRE_JSON = Path("openlibrary/components/LibraryExplorer/genre.json")
READABLE_CLAUSE = "ebook_access:[borrowable TO *]"
# Keep in sync with home_genres.MIN_GENRE_READABLE / MIN_SUBGENRE_READABLE, which filter on load.
MIN_GENRE_READABLE = 1000
MIN_SUBGENRE_READABLE = 20

# The home page's genres (#13783), in order, with the curated subject_key queries Lokesh
# spot-checked (they fold in the BISAC `fiction_*` spellings). Subgenre trees come from genre.json.
GENRES = [
    ("Absurd", "absurd", "absurd*"),
    ("Action", "action", "(fiction_action__adventure* OR action__adventure* OR action_and_adventure* OR action)"),
    ("Adventure", "adventure", "adventure*"),
    ("Crime", "crime", "(crime OR crime_fiction OR crime_fiction_fiction OR fiction_crime*)"),
    ("Drama", "drama", "drama"),
    ("Fantasy", "fantasy", "(fantasy* OR fiction_fantasy*)"),
    ("Historical", "historical", "(historical_fiction* OR fiction_historical*)"),
    ("Horror", "horror", "(horror* OR fiction_horror*)"),
    ("Humor", "humor", "(humor* OR fiction_humorous* OR comedy* OR comedies)"),
    ("LGBTQ+", "lgbtq", "(lgbtq* OR fiction_lgbtq* OR fiction_gay* OR fiction_lesbian* OR gay_men_fiction OR lesbians_fiction OR gays_fiction)"),
    ("Literary", "literary", "(literary_fiction* OR fiction_literary*)"),
    ("Mystery", "mystery", "(mystery* OR fiction_mystery__detective*)"),
    ("Mythology", "mythology", "mythology*"),
    ("Romance", "romance", "(romance* OR fiction_romance*)"),
    ("Sci-Fi", "sci-fi", "(science_fiction* OR fiction_science_fiction*)"),
    ("Thriller", "thriller", "(thriller* OR fiction_thrillers* OR fiction_suspense* OR suspense*)"),
    ("Western", "western", "(western_stories OR westerns OR western_fiction OR western OR fiction_westerns*)"),
]

# Genre subgenres whose bare subject_key tag has a dominant off-genre sense (cult->culture,
# psychological->psychological aspects, magic->stage magic, trials->clinical trials, gothic->
# architecture, slavery->history). genre.json leaves them standalone; AND them with their parent
# genre instead, so the shelf stays on-genre (thin ones then drop, like any other).
AMBIGUOUS_SUBGENRES = {"Cult", "Psychological", "Magic", "Trials", "Slavery", "Gothic"}

# The nonfiction/kids tiles, outside the genres vocabulary: (name, slug, query). Keep names in
# sync with home_genres.subject_tile_labels(), which translates them.
SUBJECTS = [
    ("Kids", "kids", "(juvenile_fiction OR juvenile_literature OR children's_fiction OR juvenile_nonfiction)"),
    ("History", "history", "history"),
    ("Biography", "biography", "(biography OR biographies)"),
    ("Philosophy", "philosophy", "philosophy"),
    ("Psychology", "psychology", "psychology"),
    ("Poetry", "poetry", "poetry"),
    ("Travel", "travel", "travel"),
    ("Science", "science", "science"),
    ("Cooking", "cooking", "(cooking OR cookery OR recipes)"),
    ("Religion", "religion", "religion"),
    ("Art", "art", "art"),
    ("Textbooks", "textbooks", "textbooks"),
]

# Subgenres for the subject tiles, spot-checked against production (raw + readable counts, topic
# noise). A subgenre searches on its own unless `intersect` ANDs it with the parent tile -- used
# where the bare tag is ambiguous out of context (profession tags are mostly novels; a kids tile
# must stay juvenile; a textbook subject must stay a textbook). (name, query, intersect).
SUBJECT_SUBGENRES = {
    "kids": [
        ("Fairy Tales", "fairy_tales*", False),
        ("Picture Books", "picture_books*", False),
        ("Adventure Stories", "adventure_and_adventurers*", False),
        ("Mystery & Detective Stories", "mystery_and_detective_stories*", False),
        ("Science Fiction", "science_fiction*", True),
        ("Humorous Stories", "humorous_stories*", False),
        ("Animals", "animals_fiction*", False),
    ],
    "history": [
        ("World War II", "world_war_1939-1945*", False),
        ("World War I", "world_war_1914-1918*", False),
        ("United States History", "united_states_history*", False),
        ("Military History", "military_history*", False),
        ("Middle Ages", "middle_ages*", False),
        ("Ancient History", "ancient_history*", False),
    ],
    "biography": [
        ("Presidents", "presidents*", False),
        ("Women", "women*", True),
        ("Authors", "authors*", True),
        ("Kings & Rulers", "kings_and_rulers*", False),
        ("Statesmen", "statesmen*", False),
        ("Artists", "artists*", True),
        ("Autobiography", "autobiography*", False),
    ],
    "philosophy": [
        ("Ethics", "ethics*", False),
        ("Logic", "logic*", False),
        ("Aesthetics", "aesthetics*", False),
        ("Metaphysics", "metaphysics*", False),
        ("Epistemology", "knowledge_theory_of*", False),
        ("Existentialism", "existentialism*", False),
        ("Ancient Philosophy", "philosophy_ancient*", False),
    ],
    "psychology": [
        ("Personality", "personality*", False),
        ("Child Psychology", "child_psychology*", False),
        ("Emotions", "emotions*", False),
        ("Social Psychology", "social_psychology*", False),
        ("Developmental Psychology", "developmental_psychology*", False),
        ("Clinical Psychology", "clinical_psychology*", False),
        ("Cognitive Psychology", "cognitive_psychology*", False),
    ],
    "poetry": [
        ("English Poetry", "english_poetry*", False),
        ("American Poetry", "american_poetry*", False),
        ("Children's Poetry", "children's_poetry*", False),
        ("Love Poetry", "love_poetry*", False),
        ("Epic Poetry", "epic_poetry*", False),
        ("Haiku", "haiku*", False),
        ("Sonnets", "sonnets*", False),
    ],
    "travel": [
        ("Description & Travel", "description_and_travel*", False),
        ("Guidebooks", "guidebooks*", False),
        ("Discovery & Exploration", "discovery_and_exploration*", False),
        ("Voyages & Travels", "voyages_and_travels*", False),
        ("National Parks", "national_parks*", False),
    ],
    "science": [
        ("Mathematics", "mathematics*", False),
        ("Natural History", "natural_history*", False),
        ("Geology", "geology*", False),
        ("Chemistry", "chemistry*", False),
        ("Physics", "physics*", False),
        ("Biology", "biology*", False),
        ("Astronomy", "astronomy*", False),
    ],
    "cooking": [
        ("Quick & Easy", "quick_and_easy_cooking*", False),
        ("Desserts", "desserts*", False),
        ("Vegetarian", "vegetarian_cooking*", False),
        ("Baking", "baking*", False),
        ("Bread", "bread*", False),
        ("Italian", "cooking_italian*", False),
        ("Vegan", "vegan_cooking*", False),
    ],
    "religion": [
        ("Bible", "bible*", False),
        ("Christianity", "christianity*", False),
        ("Theology", "theology*", False),
        ("Judaism", "judaism*", False),
        ("Islam", "islam*", False),
        ("Buddhism", "buddhism*", False),
        ("Hinduism", "hinduism*", False),
    ],
    "art": [
        ("Architecture", "architecture*", False),
        ("Painting", "painting*", False),
        ("Photography", "photography*", False),
        ("Drawing", "drawing*", False),
        ("Sculpture", "sculpture*", False),
        ("Decorative Arts", "decorative_arts*", False),
        ("Art History", "art_history*", False),
    ],
    "textbooks": [
        ("English Language", "english_language*", True),
        ("History", "history*", True),
        ("Mathematics", "mathematics*", True),
        ("Science", "science*", True),
        ("Business", "business*", True),
        ("Psychology", "psychology*", True),
        ("Chemistry", "chemistry*", True),
    ],
}

_RE_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    return _RE_SLUG.sub("-", name.lower()).strip("-")


_count_cache: dict[str, int] = {}


def readable_count(query: str, parent_query: str | None = None) -> int:
    clause = f"subject_key:{parent_query} AND subject_key:{query}" if parent_query else f"subject_key:{query}"
    q = f"{clause} AND {READABLE_CLAUSE}"
    if q in _count_cache:
        return _count_cache[q]
    url = f"{OL_SEARCH_URL}?{urllib.parse.urlencode({'q': q, 'limit': 0})}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                count = json.loads(resp.read())["numFound"]
            break
        except (urllib.error.URLError, TimeoutError, KeyError) as e:
            # A failed fetch is unknown, not zero: retrying beats silently dropping a whole shelf.
            if attempt == 2:
                raise RuntimeError(f"count lookup failed for {q!r} after 3 tries: {e}") from e
            time.sleep(3)
    _count_cache[q] = count
    time.sleep(1)  # Be polite to production.
    return count


def child(name: str, query: str, intersect: bool, parent_query: str) -> dict:
    node = {"name": name, "slug": slugify(name), "query": query, "count": readable_count(query, parent_query if intersect else None)}
    if intersect:
        node["requiresIntersection"] = True
    return node


def genre_nodes(genre_json: list[dict]) -> list[dict]:
    by_name = {g["name"]: g for g in genre_json}
    nodes = []
    for name, slug, query in GENRES:
        children = [
            child(c["name"], c["query"], c.get("requiresIntersection", False) or c["name"] in AMBIGUOUS_SUBGENRES, query) for c in by_name[name]["children"]
        ]
        nodes.append({"name": name, "slug": slug, "kind": "genre", "query": query, "count": readable_count(query), "children": children})
    return nodes


def subject_nodes() -> list[dict]:
    return [
        {
            "name": name,
            "slug": slug,
            "kind": "subject",
            "query": query,
            "count": readable_count(query),
            "children": [child(n, q, intersect, query) for n, q, intersect in SUBJECT_SUBGENRES[slug]],
        }
        for name, slug, query in SUBJECTS
    ]


def drop_thin(nodes: list[dict]) -> list[dict]:
    kept = []
    for node in nodes:
        if node["count"] < MIN_GENRE_READABLE:
            print(f"  drop tile {node['name']!r}: {node['count']} readable", file=sys.stderr)
            continue
        for thin in [c for c in node["children"] if c["count"] < MIN_SUBGENRE_READABLE]:
            print(f"  drop {node['name']}/{thin['name']}: {thin['count']} readable", file=sys.stderr)
        node["children"] = [c for c in node["children"] if c["count"] >= MIN_SUBGENRE_READABLE]
        kept.append(node)
    return kept


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--genre-json", type=Path, default=DEFAULT_GENRE_JSON, help="Genre Explorer genre.json (#13208).")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    genre_json = json.loads(args.genre_json.read_text())
    print(f"Fetching readable counts from {OL_SEARCH_URL} (1/s)...", file=sys.stderr)
    nodes = drop_thin(genre_nodes(genre_json) + subject_nodes())
    args.output.write_text(json.dumps(nodes, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(nodes)} categories to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
