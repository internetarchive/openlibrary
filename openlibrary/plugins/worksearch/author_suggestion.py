"""Author suggestions ("B-zero") for the work search results page.

No extra request: when the query names the author of one of the top works the
Solr search already returned, we surface a row linking straight to that author's
page. This covers the common "type a name -> I want that author" case (the old
Author facet) without a second Solr round-trip.

Matching the query against each top result's author is self-protecting: a title
search ("dune") returns that author's works, but the title isn't part of their
name, so nothing is surfaced. Only queries that actually name an author produce
a row.

This is a Python port of the header search modal's
``openlibrary/plugins/openlibrary/js/search-modal/authorSuggestion.js``; the two
implement the same matching rules and must be kept in sync.
"""

import unicodedata

# Only the top few results are relevant enough to surface their author.
AUTHOR_SCAN_LIMIT = 5

# At most this many author rows, so an ambiguous one-word query ("smith") can't
# flood the list.
AUTHOR_SUGGESTION_MAX = 3


def _fold(s: str) -> str:
    """Lowercase and strip diacritics so "garcia" matches "García"."""
    normalized = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in normalized if not unicodedata.combining(c)).lower()


def query_matches_name(query: str, name: str) -> bool:
    """True when the query names the author.

    Matches on word boundaries only, so a query can't match mid-word ("art" must
    not surface "Bart ..."):
     - the full name starts with the query ("leo tol" -> "Leo Tolstoy"),
     - the query contains the full name as whole words ("books by leo tolstoy"),
     - or a query word is a prefix of a name word, 3+ chars to skip
       initials/particles like "de" ("asimov"/"asim" -> "Isaac Asimov").
    """
    q = _fold(query).strip()
    full = _fold(name).strip()
    if not q or not full:
        return False
    if full.startswith(q):
        return True
    if f" {full} " in f" {q} ":
        return True
    name_tokens = full.split()
    return any(len(token) >= 3 and any(nt.startswith(token) for nt in name_tokens) for token in q.split())


def derive_authors(docs, query: str) -> list[dict[str, str]]:
    """Return the authors to suggest for the given query.

    Given the work docs from the Solr response and the query, return the authors
    of the top results whose name the query matches, in rank order, deduped by
    key and capped. Empty when the query names none of them.

    Each returned author is ``{"key": <OLxxxA>, "name": <author name>}``.
    """
    if not docs:
        return []

    seen: set[str] = set()
    authors: list[dict[str, str]] = []
    for doc in docs[:AUTHOR_SCAN_LIMIT]:
        author_key = doc.get("author_key") or []
        author_name = doc.get("author_name") or []
        key = author_key[0] if author_key else None
        name = author_name[0] if author_name else None
        if not key or not name or key in seen:
            continue
        if query_matches_name(query, name):
            seen.add(key)
            authors.append({"key": key, "name": name})
            if len(authors) >= AUTHOR_SUGGESTION_MAX:
                break
    return authors
