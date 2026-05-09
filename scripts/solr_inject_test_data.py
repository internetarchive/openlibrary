#!/usr/bin/env python3
"""
Inject synthetic but schema-realistic documents directly into local Solr
for benchmarking purposes. Distributions approximate real Open Library data.

Usage:
    python scripts/solr_inject_test_data.py [--count 50000] [--solr http://localhost:8983]
"""

import argparse
import json
import math
import random
import sys
import urllib.request
from typing import Any

SOLR = "http://localhost:8983/solr/openlibrary"

# Realistic language distribution (top 20 languages on OL)
LANGUAGES = [
    ("eng", 0.60), ("fre", 0.08), ("ger", 0.07), ("spa", 0.05), ("ita", 0.03),
    ("rus", 0.02), ("por", 0.02), ("pol", 0.01), ("nld", 0.01), ("chi", 0.01),
    ("jpn", 0.01), ("ara", 0.01), ("swe", 0.01), ("nor", 0.005), ("dan", 0.005),
    ("fin", 0.004), ("hun", 0.003), ("ces", 0.003), ("tur", 0.002), ("kor", 0.002),
]

SUBJECTS = [
    "Fiction", "History", "Science", "Biography", "Mystery", "Romance",
    "Poetry", "Philosophy", "Travel", "Cooking", "Art", "Music", "Technology",
    "Politics", "Religion", "Psychology", "Economics", "Law", "Medicine",
    "Education", "Children's literature", "Drama", "Short stories", "Essays",
    "Science fiction", "Fantasy", "Horror", "Thriller", "Adventure",
    "Self-help", "Nature", "Sports", "Military history", "Ancient history",
    "Literature", "Sociology", "Anthropology", "Archaeology", "Linguistics",
    "Mathematics", "Physics", "Chemistry", "Biology", "Astronomy",
    "Engineering", "Architecture", "Photography", "Film", "Theatre",
    "Classical literature", "American literature", "British literature",
    "World War, 1939-1945", "World War, 1914-1918", "United States -- History",
    "Great Britain -- History", "France -- History", "Germany -- History",
    "Christianity", "Islam", "Buddhism", "Judaism", "Hinduism",
    "Environmental science", "Climate change", "Economics -- History",
    "Social classes", "Race relations", "Women -- Social conditions",
    "Children -- Education", "Reading", "Libraries", "Publishing",
]

FIRST_NAMES = [
    "James", "John", "Robert", "Michael", "William", "David", "Richard",
    "Charles", "Joseph", "Thomas", "Mary", "Patricia", "Jennifer", "Linda",
    "Barbara", "Elizabeth", "Susan", "Jessica", "Sarah", "Karen", "Dorothy",
    "Agatha", "Virginia", "Emily", "Charlotte", "Jane", "George", "Henry",
    "Arthur", "Ernest", "Francis", "Samuel", "Herman", "Mark", "Leo",
    "Victor", "Alexandre", "Gustave", "Marcel", "Emile", "Anton", "Fyodor",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Wilson", "Taylor", "Thomas", "Jackson", "White", "Harris",
    "Martin", "Thompson", "Young", "Allen", "King", "Wright", "Dickens",
    "Austen", "Hemingway", "Fitzgerald", "Steinbeck", "Faulkner", "Twain",
    "Poe", "Hawthorne", "Melville", "Thoreau", "Emerson", "Whitman",
    "Hugo", "Dumas", "Flaubert", "Balzac", "Zola", "Proust", "Camus",
    "Tolstoy", "Dostoevsky", "Chekhov", "Gogol", "Turgenev", "Pushkin",
    "Goethe", "Schiller", "Kafka", "Hesse", "Mann", "Grass", "Borges",
]

TITLE_WORDS = [
    "The", "A", "An", "My", "Our", "Their", "His", "Her", "Last", "First",
    "Great", "Little", "Old", "New", "Dark", "Light", "Long", "Short",
    "House", "Garden", "River", "Mountain", "City", "Town", "Village",
    "Story", "Tale", "History", "Life", "World", "Land", "Sea", "Sky",
    "Man", "Woman", "Child", "King", "Queen", "Prince", "War", "Peace",
    "Time", "Death", "Love", "Hope", "Fear", "Fire", "Ice", "Wind",
    "Journey", "Road", "Path", "Door", "Window", "Mirror", "Shadow",
    "Blood", "Bone", "Heart", "Mind", "Soul", "Spirit", "Dream", "Memory",
    "Secret", "Hidden", "Lost", "Found", "Broken", "Complete", "Final",
]

EBOOK_ACCESS = [
    ("no_ebook", 0.55),
    ("printdisabled", 0.25),
    ("borrowable", 0.15),
    ("public", 0.05),
]


def weighted_choice(choices: list[tuple[Any, float]]) -> Any:
    r = random.random()
    cumulative = 0.0
    for value, weight in choices:
        cumulative += weight
        if r < cumulative:
            return value
    return choices[-1][0]


def make_title() -> str:
    n = random.choices([2, 3, 4, 5], weights=[0.3, 0.4, 0.2, 0.1])[0]
    return " ".join(random.sample(TITLE_WORDS, min(n, len(TITLE_WORDS))))


def make_author_key(author_idx: int) -> str:
    return f"/authors/OL{author_idx}A"


def make_work(work_idx: int, author_pool: list[int]) -> dict[str, Any]:
    # Pick 1-3 authors (power-law: most works have 1 author)
    num_authors = random.choices([1, 2, 3], weights=[0.85, 0.12, 0.03])[0]
    author_indices = random.sample(author_pool, min(num_authors, len(author_pool)))

    # Edition count: power-law distribution (most works have few editions)
    edition_count = max(1, int(random.paretovariate(2) * 3))
    edition_count = min(edition_count, 500)

    first_publish_year = random.choices(
        range(1800, 2025),
        weights=[
            # Older books less common, peak around 1980-2010
            max(1, int(10 * math.exp(-0.005 * (2000 - y) ** 2 + 0.5))) if y < 2000
            else max(1, int(50 - (y - 2000)))
            for y in range(1800, 2025)
        ],
    )[0]

    # Subjects: 1-8 subjects per work
    num_subjects = random.choices([1, 2, 3, 4, 5, 6, 7, 8], weights=[0.15, 0.20, 0.20, 0.15, 0.12, 0.10, 0.05, 0.03])[0]
    subjects = random.sample(SUBJECTS, min(num_subjects, len(SUBJECTS)))

    # Languages
    num_langs = random.choices([1, 2, 3], weights=[0.88, 0.10, 0.02])[0]
    langs = [weighted_choice(LANGUAGES) for _ in range(num_langs)]

    ebook = weighted_choice(EBOOK_ACCESS)
    has_fulltext = ebook in ("printdisabled", "borrowable", "public")

    # Ratings (sparse - most works have no ratings)
    ratings_count = int(random.paretovariate(3)) if random.random() < 0.2 else 0
    ratings_count = min(ratings_count, 50000)
    ratings_average = random.uniform(3.0, 5.0) if ratings_count > 0 else 0.0
    ratings_sortable = ratings_average if ratings_count >= 10 else 0.0

    author_keys = [make_author_key(i) for i in author_indices]
    author_names = [
        f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        for _ in author_indices
    ]
    author_facets = [f"{name} | {key}" for name, key in zip(author_names, author_keys)]

    title = make_title()
    doc: dict[str, Any] = {
        "key": f"/works/OL{work_idx}W",
        "type": "work",
        "title": title,
        # title_suggest and title_sort are auto-populated via copyField from title
        "edition_count": edition_count,
        "first_publish_year": first_publish_year,
        "author_key": author_keys,
        "author_name": author_names,
        "author_facet": author_facets,
        "language": langs,
        "subject": subjects,
        "subject_facet": subjects,
        "subject_key": [s.lower().replace(" ", "_") for s in subjects],
        "has_fulltext": has_fulltext,
        "ebook_access": ebook,
        "ratings_count": ratings_count,
        "ratings_average": round(ratings_average, 2) if ratings_count > 0 else 0.0,
        "ratings_sortable": round(ratings_sortable, 2),
        "ratings_count_1": int(ratings_count * random.uniform(0.02, 0.08)),
        "ratings_count_2": int(ratings_count * random.uniform(0.04, 0.10)),
        "ratings_count_3": int(ratings_count * random.uniform(0.08, 0.15)),
        "ratings_count_4": int(ratings_count * random.uniform(0.20, 0.30)),
        "ratings_count_5": int(ratings_count * random.uniform(0.40, 0.60)),
        "readinglog_count": int(random.paretovariate(3)) if random.random() < 0.15 else 0,
        "want_to_read_count": int(random.paretovariate(3)) if random.random() < 0.12 else 0,
        "currently_reading_count": int(random.paretovariate(3)) if random.random() < 0.05 else 0,
        "already_read_count": int(random.paretovariate(3)) if random.random() < 0.10 else 0,
        # Note: "text" field is populated automatically via copyField rules in schema
    }
    return doc


def post_batch(docs: list[dict], solr_url: str) -> None:
    payload = json.dumps(docs).encode("utf-8")
    req = urllib.request.Request(
        f"{solr_url}/update?wt=json",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            if result.get("responseHeader", {}).get("status", 0) != 0:
                print(f"ERROR: {result}", file=sys.stderr)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"HTTP {e.code} on batch, retrying one-by-one: {body[:500]}", file=sys.stderr)
        for doc in docs:
            single_payload = json.dumps([doc]).encode("utf-8")
            single_req = urllib.request.Request(
                f"{solr_url}/update?wt=json",
                data=single_payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(single_req, timeout=10) as r:
                    pass
            except Exception as e2:
                print(f"  Skipping doc {doc.get('key')}: {e2}", file=sys.stderr)


def commit(solr_url: str) -> None:
    req = urllib.request.Request(
        f"{solr_url}/update?commit=true&wt=json",
        data=b"",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read())
        status = result.get("responseHeader", {}).get("status", -1)
        print(f"Commit status: {status}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject synthetic OL data into local Solr")
    parser.add_argument("--count", type=int, default=50000, help="Number of work documents to inject")
    parser.add_argument("--solr", default=SOLR, help="Solr base URL")
    parser.add_argument("--batch-size", type=int, default=500, help="Documents per update batch")
    parser.add_argument("--start-idx", type=int, default=100000, help="Starting work index (avoid collisions with real data)")
    args = parser.parse_args()

    solr_url = args.solr
    count = args.count
    batch_size = args.batch_size
    start_idx = args.start_idx

    random.seed(42)

    # Create a pool of author indices (realistic: many works share authors)
    num_authors = max(100, count // 10)
    author_pool = list(range(start_idx, start_idx + num_authors))
    print(f"Generating {count} works with {num_authors} authors (pool)")

    batch: list[dict] = []
    total_sent = 0

    for i in range(count):
        work_idx = start_idx + i
        doc = make_work(work_idx, author_pool)
        batch.append(doc)

        if len(batch) >= batch_size:
            post_batch(batch, solr_url)
            total_sent += len(batch)
            batch = []
            if total_sent % 5000 == 0:
                print(f"  Sent {total_sent}/{count} documents...")

    if batch:
        post_batch(batch, solr_url)
        total_sent += len(batch)

    print(f"Sent {total_sent} documents total. Committing...")
    commit(solr_url)
    print("Done.")


if __name__ == "__main__":
    main()
