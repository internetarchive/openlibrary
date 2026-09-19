"""Promote high-volume agents out of the ``other`` bucket automatically.

Both the crawler monitor (``log_recent_bot_traffic``) and the partner API
monitor classify traffic against hardcoded allowlists. Anything off the list
collapses into a single ``other`` series and the agent's name -- which we
already have in hand -- is discarded, so every new partner and crawler lands in
``other`` and stays there until someone edits source.

The monitors tick once a minute over the previous minute of logs, but the
volume that justifies a dedicated label accrues over hours: an agent worth
labelling may send nothing at all in any given minute. So the promotion
decision and the metric emission are separated here. Emission is unchanged --
each tick still reports that tick's counts. Only the choice of *which names get
their own label* is made over an accumulated window.

Cardinality is bounded by ``max_labels`` rather than by ``min_count``, which
keeps the mechanism working even if the threshold is mistuned: the ranking
picks the right agents either way, and the threshold only decides how far down
the long tail it reaches.
"""

from collections import deque
from collections.abc import Callable, Iterable, Mapping

from scripts.monitoring.utils import GraphiteEvent, graphite_safe

# User-Agent is attacker-controlled and a promoted agent mints a Graphite path.
# graphite_safe() bounds the character set but not the length, so bound it here.
# The longest real partner name we currently label is 31 characters, so this
# leaves genuine names room while still keeping a 4KB header out of the metric tree.
MAX_LABEL_LENGTH = 48

OTHER_LABEL = "other"

# Labels log_recent_bot_traffic already emits into the same bucket from bash.
# A promoted agent must never mint one of these: monitor.py submits after the
# bash half has run, so it would silently overwrite the real value.
RESERVED_LABELS = frozenset({OTHER_LABEL, "non_bot"})

# 60 one-minute ticks == 1 hour.
DEFAULT_WINDOW_TICKS = 60


def safe_label(name: str) -> str:
    """Turn an agent name into a bounded, Graphite-safe metric path segment.

    Truncation can collide two long names that share a prefix; they then share
    a series, which is preferable to an unbounded path. Labels that bash already
    emits into the same bucket are reserved, so an agent cannot overwrite them by
    naming itself after one.
    """
    label = graphite_safe(name)[:MAX_LABEL_LENGTH].strip("._-")
    if not label:
        return "unknown"
    if label in RESERVED_LABELS:
        return f"{label}_agent"
    return label


def parse_uniq_c(output: str) -> list[tuple[int, str]]:
    """Parse ``uniq -c`` style ``<count> <value>`` lines, skipping malformed ones."""
    rows = []
    # Deliberately not splitlines(): it also breaks on \v, \f and \x1c-\x1e, which
    # would let one crafted User-Agent forge a second row with a count of its choice.
    for line in output.split("\n"):
        count, _, value = line.strip().partition(" ")
        if not (value := value.strip()):
            continue
        try:
            rows.append((int(count), value))
        except ValueError:
            continue
    return rows


def tally(rows: Iterable[tuple[int, str]], key: Callable[[str], str]) -> dict[str, int]:
    """Sum counts by ``key(value)``, since distinct values can share a label."""
    counts: dict[str, int] = {}
    for count, value in rows:
        label = key(value)
        counts[label] = counts.get(label, 0) + count
    return counts


class RollingPromoter:
    """Chooses which agents get their own label, over a rolling window of ticks.

    :param min_count: floor an agent must reach across the whole window
    :param max_labels: hard cap on how many agents are promoted at once
    :param window_ticks: how many ticks the window holds
    """

    def __init__(self, min_count: int, max_labels: int, window_ticks: int = DEFAULT_WINDOW_TICKS):
        self.min_count = min_count
        self.max_labels = max_labels
        self._ticks: deque[dict[str, int]] = deque(maxlen=window_ticks)

    @property
    def window_ticks(self) -> int:
        # deque.maxlen is never None here; the constructor always sets it.
        return self._ticks.maxlen or 0

    def observe(self, counts: Mapping[str, int]) -> None:
        """Record one tick's counts, ageing out the oldest tick if the window is full."""
        self._ticks.append(dict(counts))

    def totals(self) -> dict[str, int]:
        """Per-label totals across the whole window."""
        totals: dict[str, int] = {}
        for tick in self._ticks:
            for label, count in tick.items():
                totals[label] = totals.get(label, 0) + count
        return totals

    def promoted(self, pinned: Iterable[str] = ()) -> set[str]:
        """The labels that have earned their own series in the current window.

        Pinned names are excluded from the ranking. They already have a
        guaranteed series, so letting them compete would spend slots on agents
        that do not need them and starve the new agents this exists to find.
        """
        pinned = set(pinned)
        eligible = [(count, label) for label, count in self.totals().items() if count >= self.min_count and label not in pinned]
        # Rank by windowed volume; the name breaks ties so the set is deterministic.
        eligible.sort(key=lambda row: (-row[0], row[1]))
        return {label for _, label in eligible[: self.max_labels]}

    def split(self, counts: Mapping[str, int], pinned: Iterable[str] = ()) -> dict[str, int]:
        """Observe a tick's counts and label them for submission.

        Promoted and pinned names keep their own key; everything else sums into
        ``other``. Every kept label is reported every tick, at zero if it sent
        nothing: an agent near the floor sends nothing in most individual
        minutes, and emitting gaps instead of zeros renders those series as
        broken sawtooths on a stacked graph. Pinned names bypass the floor and
        do not compete for slots, so they never lose their series.
        """
        self.observe(counts)
        keep = self.promoted(pinned) | set(pinned)
        labelled = dict.fromkeys(keep, 0)
        labelled[OTHER_LABEL] = 0
        for label, count in counts.items():
            if label in keep:
                labelled[label] = labelled.get(label, 0) + count
            else:
                labelled[OTHER_LABEL] += count
        return labelled


def promoted_events(
    counts: Mapping[str, int],
    promoter: RollingPromoter,
    prefix: str,
    timestamp: int,
    pinned: Iterable[str] = (),
) -> list[GraphiteEvent]:
    """Label one tick's counts and build the Graphite events for them.

    Kept separate from submission so the metric paths can be asserted without a
    socket: ``<prefix>.other`` is part of the contract with the dashboards, not
    an implementation detail.
    """
    return [GraphiteEvent(path=f"{prefix}.{label}", value=float(count), timestamp=timestamp) for label, count in promoter.split(counts, pinned=pinned).items()]
