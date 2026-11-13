#!/usr/bin/env python3
"""
Edition Scorecard totals for a Tasks project's frozen list: each edition as it stood when the list was frozen, and now.

The start side is rebuilt from each edition's revision history, so re-running this later gives start-vs-then with no saved state.
Only the edition is read as of the start; its work, authors, Solr work doc and IA metadata are today's.

PYTHONPATH=. python ./scripts/initiative_scorecard.py /olsystem/etc/openlibrary.yml --slug most-read-2026-11 --out /tmp/scores.json
"""

import json
import logging
import statistics
from collections import Counter
from datetime import UTC, datetime

from infogami import config  # noqa: F401 side effects may be needed
from openlibrary.contribute import initiatives
from openlibrary.setup import setup_for_script
from openlibrary.utils.request_context import site as request_site
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

logger = logging.getLogger("openlibrary.initiative_scorecard")


def as_of(site, key: str, when: datetime):
    """The edition as it stood at ``when``, or None if it didn't exist yet."""
    for v in site.versions({"key": key, "sort": "-created", "limit": 500}):
        created = v.created if v.created.tzinfo else v.created.replace(tzinfo=UTC)
        if created <= when:
            return site.get(key, v.revision)
    return None


def current(site, key: str):
    """The edition now, following a merge's redirect."""
    doc = site.get(key)
    if doc and doc.type.key == "/type/redirect":
        doc = site.get(doc.location)
    return doc


def card(edition) -> dict | None:
    if not edition or not (sc := edition.scorecard):
        return None
    return {
        "score": sc.score,
        "sections": {s.name: s.score for s in sc.get_sections()},
        "passing": sorted(c.name for c in sc.passing_checks),
    }


def summary(cards: list[dict]) -> dict:
    scores = [c["score"] for c in cards]
    return {
        "editions": len(scores),
        "total": sum(scores),
        "mean": round(statistics.mean(scores), 1) if scores else 0,
        "median": statistics.median(scores) if scores else 0,
        # How many editions pass each check, keyed by check name: shows which details moved.
        "passing": dict(sorted(Counter(n for c in cards for n in c["passing"]).items())),
    }


def main(ol_config: str, slug: str = initiatives.MOST_READ.slug, since: str | None = None, limit: int = 0, out: str | None = None):
    """
    :param slug: the project's slug, as in /tasks?initiative=<slug>
    :param since: ISO time to score the start from; defaults to when the list was frozen
    :param limit: score only the first N editions, for a quick check
    :param out: write per-edition scores and the summary here as JSON
    """
    setup_for_script(ol_config)
    site = request_site.get()
    frozen = site.store.get(f"contribute-initiative-{slug}")
    if not frozen:
        raise SystemExit(f"No frozen list for {slug!r}")
    start = datetime.fromisoformat(since or frozen["frozen_at"])
    start = start if start.tzinfo else start.replace(tzinfo=UTC)
    keys = [k for k, *_ in frozen["editions"]][: limit or None]

    rows, skipped = [], []
    for i, key in enumerate(keys, 1):
        try:
            before, after = card(as_of(site, key, start)), card(current(site, key))
        except Exception:
            logger.exception("Failed on %s", key)
            before = after = None
        if before and after:
            rows.append({"key": key, "start": before, "now": after})
        else:
            skipped.append(key)
        if i % 100 == 0:
            print(f"{i}/{len(keys)}", flush=True)

    result: dict = {
        "slug": slug,
        "start_at": start.isoformat(timespec="seconds"),
        "now_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "skipped": skipped,
        "start": summary([r["start"] for r in rows]),
        "now": summary([r["now"] for r in rows]),
    }
    if out:
        with open(out, "w") as f:
            json.dump(result | {"editions": rows}, f, indent=1)

    s, n = result["start"], result["now"]
    print(f"\n{slug}: {s['editions']} editions scored, {len(skipped)} skipped")
    print(f"{'':10}{'start ' + result['start_at'][:10]:>20}{'now ' + result['now_at'][:10]:>20}{'change':>10}")
    for label in ("total", "mean", "median"):
        print(f"{label:10}{s[label]:>20,}{n[label]:>20,}{round(n[label] - s[label], 1):>+10,}")
    print("\nEditions passing each check that changed:")
    for name in sorted(set(s["passing"]) | set(n["passing"])):
        a, b = s["passing"].get(name, 0), n["passing"].get(name, 0)
        if a != b:
            print(f"  {name:22}{a:>6} -> {b:<6}({b - a:+})")


if __name__ == "__main__":
    FnToCLI(main).run()
