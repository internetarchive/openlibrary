"""Fixture loaders for the phase 1 walkthrough.

Outside evidence, the demo set, practice tasks and status states are JSON in
``fixtures/``. Live lookups replace the evidence and demo loaders in phase 2;
the callers do not change.
"""

import json
from functools import cache
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def _load(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@cache
def load_demo_books() -> list[dict]:
    """The demo set, most readers first. Readers counts are illustrative."""
    books = _load(FIXTURES / "demo_books.json")
    return sorted(books, key=lambda b: -b.get("readers", 0))


@cache
def load_evidence(isbn13: str) -> dict | None:
    path = FIXTURES / "evidence" / f"{isbn13}.json"
    return _load(path) if path.exists() else None


@cache
def load_practice() -> list[dict]:
    return [_load(p) for p in sorted((FIXTURES / "practice").glob("*.json"))]


def get_practice(key: str) -> dict | None:
    return next((p for p in load_practice() if p["key"] == key), None)


@cache
def load_status() -> list[dict]:
    return _load(FIXTURES / "status.json")


def _demo_entry(isbn13: str | None) -> dict | None:
    if not isbn13:
        return None
    return next((b for b in load_demo_books() if b["isbn13"] == isbn13), None)


def demo_readers(isbn13: str | None) -> int:
    entry = _demo_entry(isbn13)
    return entry.get("readers", 0) if entry else 0


def demo_cover_id(isbn13: str | None) -> int | None:
    entry = _demo_entry(isbn13)
    return entry.get("cover_id") if entry else None
