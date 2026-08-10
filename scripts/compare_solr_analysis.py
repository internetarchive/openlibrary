#!/usr/bin/env python3
"""
Compare Solr's index-time and query-time analysis of the same text.

Solr's admin Analysis UI shows this, but reading it by eye is slow and it is
easy to miscount positions. This prints both token streams and answers the one
question that matters for phrase matching:

    can a phrase query built from this text match a document indexed from it?

Why positions matter
--------------------
A field has two analyzer chains, `index` and `query`. Whatever the index chain
emits is what is stored; whatever the query chain emits is what gets looked up.
A phrase query matches only if each query token is found in the index at the
same relative position. So the two chains must agree on positions, not just on
which terms survive. They frequently do not, because they are configured
differently on purpose.

Note the index side may legitimately emit EXTRA tokens the query side does not.
`text_en_splitting` runs wordDelimiterGraph with catenateWords=1 when indexing
and 0 when querying, so "Spider-Man" indexes an extra catenated "spiderman"
that the query never produces. That is by design. Only tokens the query needs
and the index lacks can break a match, so that is what this script reports --
a naive "are the streams equal" check reports false alarms here.

Usage
-----
    # against your local dev Solr
    python3 scripts/compare_solr_analysis.py "The Mark of the Crown"

    # a specific field, several strings, exit non-zero if any break
    python3 scripts/compare_solr_analysis.py --field alternative_title \\
        "The Mark of the Crown" "The Lord of the Rings"

    # compare two cores, e.g. a baseline against a schema you are testing
    python3 scripts/compare_solr_analysis.py --core openlibrary --vs mytest "A Tale of Two Cities"

Exits non-zero if any input cannot phrase-match, so it works in a test loop.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_CASES = [
    # Two consecutive stopwords -- the case from issue #5393.
    "The Mark of the Crown",
    "The Lord of the Rings",
    # A single stopword between terms; only one position hole.
    "A Tale of Two Cities",
    # Hyphenation, which exercises wordDelimiterGraph rather than stopwords.
    "Spider-Man",
]


def analyze(base_url: str, core: str, field: str, text: str) -> tuple[list[dict], list[dict]]:
    """Return the final (index, query) token lists for `text`."""
    qs = urllib.parse.urlencode(
        {
            "analysis.fieldname": field,
            "analysis.fieldvalue": text,
            "analysis.query": text,
            "wt": "json",
        }
    )
    url = f"{base_url}/solr/{core}/analysis/field?{qs}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Solr returned {exc.code} for core {core!r}, field {field!r}.\n{url}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Could not reach Solr at {base_url} ({exc.reason}). Is your dev stack up?") from exc

    try:
        body = payload["analysis"]["field_names"][field]
    except KeyError:
        raise SystemExit(f"Solr did not analyze field {field!r}. Does it exist in the schema?") from None

    # Each side is [filter_name, tokens, filter_name, tokens, ...]; we want the
    # last token list, i.e. what the chain finally emits.
    return body["index"][-1], body["query"][-1]


def phrase_can_match(index_tokens: list[dict], query_tokens: list[dict]) -> list[tuple[str, int]]:
    """Query tokens that the index lacks at that position. Empty means it matches."""
    indexed = {(t["text"], t["position"]) for t in index_tokens}
    return [(t["text"], t["position"]) for t in query_tokens if (t["text"], t["position"]) not in indexed]


def render(tokens: list[dict]) -> str:
    return " ".join(f"{t['text']}@{t['position']}" for t in tokens) or "(none)"


def check(base_url: str, core: str, field: str, text: str, verbose: bool) -> bool:
    index_tokens, query_tokens = analyze(base_url, core, field, text)
    missing = phrase_can_match(index_tokens, query_tokens)
    status = "ok  " if not missing else "BROKEN"
    print(f"  [{status}] {text!r}")
    if verbose or missing:
        print(f"           index: {render(index_tokens)}")
        print(f"           query: {render(query_tokens)}")
    if missing:
        listed = ", ".join(f"{t}@{p}" for t, p in missing)
        print(f"           the query needs {listed}, which the index does not have at that position")
        print("           => a phrase query for this text cannot match a doc indexed from it")
    return not missing


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("text", nargs="*", help="strings to analyze (default: a built-in set covering stopwords and hyphenation)")
    parser.add_argument("--url", default="http://localhost:8983", help="Solr base URL (default: %(default)s)")
    parser.add_argument("--core", default="openlibrary", help="core to analyze against (default: %(default)s)")
    parser.add_argument("--vs", metavar="CORE", help="also run against this core and compare, e.g. a schema variant")
    parser.add_argument("--field", default="text", help="field whose analysis chain to use (default: %(default)s)")
    parser.add_argument("-v", "--verbose", action="store_true", help="always print both token streams")
    args = parser.parse_args()

    cases = args.text or DEFAULT_CASES
    base = args.url.rstrip("/")

    print(f"core={args.core}  field={args.field}")
    results = {case: check(base, args.core, args.field, case, args.verbose) for case in cases}
    ok = all(results.values())

    if args.vs:
        print(f"\ncore={args.vs}  field={args.field}")
        other = {case: check(base, args.vs, args.field, case, args.verbose) for case in cases}
        print("\nDifferences:")
        changed = False
        for case in cases:
            if results[case] != other[case]:
                changed = True
                before, after = ("BROKEN", "ok") if other[case] else ("ok", "BROKEN")
                print(f"  {case!r}: {args.core}={before} -> {args.vs}={after}")
        if not changed:
            print("  none - both cores behave identically on these inputs")
        ok = ok and all(other.values())

    print()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
