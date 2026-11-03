"""Which books need a hand: the active initiative's editions that still have a gap in the fields asked for."""

import random
from collections.abc import Iterator
from dataclasses import dataclass, field

from openlibrary.contribute import initiatives
from openlibrary.utils.request_context import site


@dataclass(frozen=True)
class Candidate:
    edition: object
    readers: int | None = None
    # Fields enough people couldn't find; the edition is no longer a task for them.
    not_found: frozenset[str] = field(default_factory=frozenset)


def candidates(fields: tuple[str, ...], batch: int = 50) -> Iterator[Candidate] | None:
    """The initiative's editions with an open gap in ``fields``, in random order.

    None while the initiative's gaps are still being built. Editions load a batch at a time, so a caller that stops early never fetches them all.
    """
    if (gaps := initiatives.get_gaps()) is None:
        return None
    wanted = set(fields)
    picks = [[key, readers, skipped] for key, readers, open_fields, skipped in gaps if wanted.intersection(open_fields)]
    return _load(picks, batch)


def _load(picks: list[list], batch: int) -> Iterator[Candidate]:
    picks = random.sample(picks, len(picks))
    for i in range(0, len(picks), batch):
        chunk = picks[i : i + batch]
        editions = {e.key: e for e in site.get().get_many([key for key, _readers, _skipped in chunk])}
        yield from (Candidate(editions[key], readers, frozenset(skipped)) for key, readers, skipped in chunk if key in editions)
