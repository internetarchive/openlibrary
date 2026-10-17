"""Find covers whose record points into an archive.org zip that does not hold them.

That state is what lost covers from ``covers_0014_62`` (#9836): the batch was
zipped and uploaded while still open, then finalized by a later run, so some of
its later covers now redirect into a zip that holds only 4,073. A short zip
alone is ordinary, and so is a finalized batch; only the pairing is a loss, and
both halves are public:

- archive.org's listing of each zip says what the zip holds;
- ``covers.openlibrary.org/b/id/<id>.json`` has a ``filename`` field that is
  either a local path or the zip the cover redirects into.

For every expected zip, count its listing. For each zip short of
``BATCH_SIZE``, read ``filename`` for its missing IDs (all of them when there are
at most ``SAMPLE_ALL_UPTO``, otherwise the first, the last and three evenly
spaced) and classify the batch by the worst one:

- ``ok``: the zip holds the whole batch;
- ``short_no_record``: every sampled missing ID is a 404. That reads as "no
  record, so no pointer can break", but it is also what a row lost after
  finalize looks like; this check cannot tell the two apart;
- ``partial``: a missing ID still points at a local file (a partial upload, the
  loss's precondition; known to happen for covers that failed to archive).
  ``serves`` is the status of a HEAD on one such cover's image with
  ``?default=false``: only 200 means it is still served locally, with no
  archived copy. A 302 means the cover redirects into the zip after all (the
  redirect is gated on the row's ``uploaded`` flag, not on ``filename``), so the
  batch is reported as LOSS;
- ``LOSS``: a missing ID points at this very zip, and a second, uncached read of
  the listing gives the same count;
- ``missing_zip``: an expected zip is absent from its item, on two reads of the
  item's metadata. ``expected_by`` says why it was expected: ``known`` or
  ``baseline`` (named in that file) or ``pointer`` (a cover's ``filename`` read
  this run points into it) are evidence it existed, and exit 1;
  ``below_newest`` (its batch is below the newest zip) is only an inference,
  and exits 3. Batches above the newest zip are backlog, never
  ``missing_zip``. A deleted newest zip is caught through the baseline or,
  without one, through pointers read in the batch above the newest zip listed;
  it is missed only if no cover was ever finalized into it, so nothing is lost;
- ``indeterminate``: anything else: another zip, an unknown filename shape, a
  failed request, a listing that is unreadable, empty or cut short (no closing
  ``</table>`` and ``</html>``), a LOSS whose re-read disagrees, or an item that
  lists no zips (archive.org answers a missing item with 200 and ``{}``). Never
  read as either verdict. A listing truncated the same way on both reads is not
  caught.

The sampler catches tail-shaped losses by construction, since the last missing
ID is always sampled. A loss scattered among legitimately deleted IDs is caught
only when a sampled ID lands on it; ``sampled`` and ``missing_count`` on every
row say how much of the gap was seen.

Known losses are listed with their evidence in ``cover_archival_known_losses.json``.
Each is checked on every run, whatever the scope, and reported as ``known``
while its ``missing_count`` is unchanged. One that grows is a new loss; one that
shrinks has been at least partly repaired and the file needs updating.

The controls run first, and no verdict is printed unless all pass:

- positive: cover 14627720 reads as LOSS. Once ``covers_0014_62`` is repaired
  there is no live positive case, and the summary says ``positive_control:
  fixture_only``: from then on only the recorded test fixture exercises it;
- negative: cover 14615000 points at ``covers_0014_61.zip`` and is listed in it;
- ``serves``: a cover from the open batch has a local ``filename`` and answers
  200, and cover 999999999 does not. The open batch is found each run by
  probing up from the newest zip for the newest cover ID; archival never zips it;
- every known loss still reads as LOSS, or has shrunk.

By default a run checks the newest ``MAIN_BATCHES`` full-size batch numbers,
counting down from the newest zip across item boundaries. ``--items`` checks
whole items instead, in any ``--tiers``; the periodic census of older zips
calls this same code that way, and must pass its own ``--max-requests``.

Only ``id`` and ``filename`` are kept from each ``/b/id/<id>.json`` response
(data minimisation); raw bodies are never logged or stored.

Output: one JSON line per zip on stdout, ``{batch, listing_count,
missing_count, sampled, verdict, evidence_ids}``, plus ``serves`` on partial
rows, ``known`` on allowlisted ones and ``error`` where one applies. Then one
summary line on stderr, always, with no ``batch`` key. Exit codes, most urgent
first when several apply:

- 2: a control failed; no verdicts printed;
- 1: a LOSS row that is not a known loss, a known loss that grew, or a
  ``missing_zip`` with evidence. A printed LOSS row stands even if the run
  later stops;
- 5: a known loss shrank, so the list is stale;
- 4: request cap reached; the rows printed are not a census;
- 3: indeterminate, an inferred ``missing_zip``, or any unexpected error;
- 0: clean.

Usage:
    python scripts/monitoring/cover_archival_check.py
    python scripts/monitoring/cover_archival_check.py --items 0012 0013 --tiers "" s m l --max-requests 3000
"""

import argparse
import json
import re
import sys
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpx

BATCH_SIZE = 10_000
ITEM_SIZE = 1_000_000
BATCHES_PER_ITEM = ITEM_SIZE // BATCH_SIZE
TIERS = ("", "s", "m", "l")
DEFAULT_ITEM = "0014"
FIRST_ZIP_ITEM = "0008"  # code.py redirects only IDs >= 8,000,000 into zips
MAIN_BATCHES = 100
SAMPLE_ALL_UPTO = 6
DEFAULT_MAX_REQUESTS = 250
UA = "openlibrary-cover-archival-check/1.0 (+https://github.com/internetarchive/openlibrary/issues/13762)"
KNOWN_LOSSES_FILE = Path(__file__).with_name("cover_archival_known_losses.json")

POSITIVE_CONTROL_ID = 14627720
NEGATIVE_CONTROL_ID = 14615000
SERVES_ABSENT_ID = 999999999
# The open-batch probe stops within this many IDs of the newest cover, then
# tries candidates this far apart below it, so it never lands on a cover mid-upload.
NEWEST_ID_RESOLUTION = 100
OPEN_BATCH_CANDIDATES = 3
# The newest-ID search's first gallop step, and the run of consecutive IDs without
# a record that marks the end of the ID space (the rule #13766's S3 uses).
GALLOP_FIRST_STEP = BATCH_SIZE
END_OF_IDS_TAIL = 10
MAX_NEWEST_RESUMES = 5
# IDs tried down from the end of the newest zip's batch, in case one was deleted.
FLOOR_CANDIDATES = 5
# IDs read in the batch above the newest zip: a deleted newest zip that covers
# still point into shows up through them as a pointer-evidenced missing_zip.
ABOVE_TOP_OFFSETS = (0, BATCH_SIZE // 2, BATCH_SIZE - 1)

EXIT_OK, EXIT_LOSS, EXIT_CONTROL, EXIT_INDETERMINATE, EXIT_BUDGET, EXIT_STALE = 0, 1, 2, 3, 4, 5

ZIP_NAME = re.compile(r"(?:([sml])_)?covers_(\d{4})_(\d{2})")
ZIP_POINTER = re.compile(r"covers_(\d{4})/covers_\1_(\d{2})\.zip")
LOCAL_POINTER = re.compile(r"\d{4}/\d{2}/\d{2}/[^/]+\.jpg")
LISTING_ENTRY = re.compile(r"(\d{10})(?:-[SML])?\.jpg")
LISTING_END = re.compile(r"</table>.*</html>", re.DOTALL | re.IGNORECASE)

# Verdict precedence: the worst sampled ID decides the batch.
SEVERITY = ["ok", "short_no_record", "partial", "indeterminate", "LOSS"]


class BudgetExceeded(Exception):
    pass


class NewestIdNotFound(Exception):
    def __init__(self, tried: list[int]):
        super().__init__(f"no tail of {END_OF_IDS_TAIL} missing IDs confirmed after {len(tried)} probes")
        self.tried = tried


def first_live_in_tail(exists: Callable[[int], bool], start: int, tail: int = END_OF_IDS_TAIL) -> int | None:
    """The first of ``tail`` consecutive IDs from ``start`` that exists, or None if none does.

    None means ``start`` begins a run of ``tail`` missing IDs: the end of the ID
    space, unless more than ``tail - 1`` consecutive IDs were deleted.
    """
    return next((i for i in range(start, start + tail) if exists(i)), None)


def newest_existing_id(
    exists: Callable[[int], bool],
    floor: int,
    first_step: int,
    resolution: int,
    tail: int = END_OF_IDS_TAIL,
    max_resumes: int = MAX_NEWEST_RESUMES,
) -> int:
    """An existing ID within ``resolution`` below the first run of ``tail`` missing IDs above ``floor``.

    Gallops up from ``floor`` (which must exist), bisects to ``resolution``, then
    checks that the ``tail`` IDs from the first miss are all missing. A deleted ID
    on a probe point ends the search early; the tail check sees covers above it
    and the search resumes from there, at most ``max_resumes`` times. So the
    result is robust to up to ``tail - 1`` consecutive deleted IDs.
    Raises NewestIdNotFound, listing every ID probed, when resumes run out.
    """
    tried: list[int] = []

    def probe(i: int) -> bool:
        tried.append(i)
        return exists(i)

    lo = floor
    for _ in range(max_resumes + 1):
        step = first_step
        while probe(lo + step):
            lo, step = lo + step, step * 2
        hi = lo + step
        while hi - lo > resolution:
            mid = (lo + hi) // 2
            if probe(mid):
                lo = mid
            else:
                hi = mid
        live = first_live_in_tail(probe, hi + 1, tail - 1)
        if live is None:
            return lo
        lo = live
    raise NewestIdNotFound(tried)


class Http:
    """GETs and HEADs with a hard request cap, a delay between requests and an identifying UA."""

    def __init__(self, max_requests: int = DEFAULT_MAX_REQUESTS, delay: float = 1.0, client: httpx.Client | None = None):
        self.max_requests = max_requests
        self.delay = delay
        self.count = 0
        self.client = client or httpx.Client(headers={"User-Agent": UA}, timeout=120, follow_redirects=True)

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        if self.count >= self.max_requests:
            raise BudgetExceeded(f"request cap of {self.max_requests} reached before {url}")
        if self.count and self.delay:
            time.sleep(self.delay)
        self.count += 1
        return self.client.request(method, url, **kwargs)

    def get(self, url: str) -> httpx.Response:
        return self.request("GET", url)

    def head(self, url: str) -> httpx.Response:
        return self.request("HEAD", url, follow_redirects=False)


@dataclass(frozen=True)
class Zip:
    tier: str
    item: str
    batch: int

    @property
    def name(self) -> str:
        return f"{item_name(self.tier, self.item)}_{self.batch:02d}"

    @property
    def first_id(self) -> int:
        return int(self.item) * ITEM_SIZE + self.batch * BATCH_SIZE

    @property
    def listing_url(self) -> str:
        return f"https://archive.org/download/{item_name(self.tier, self.item)}/{self.name}.zip/"


def item_name(tier: str, item: str) -> str:
    return f"{tier}_covers_{item}" if tier else f"covers_{item}"


def zip_from_name(name: str) -> Zip:
    m = ZIP_NAME.fullmatch(name)
    if not m:
        raise ValueError(f"not a zip batch name: {name!r}")
    return Zip(m[1] or "", m[2], int(m[3]))


def zip_for_id(cover_id: int, tier: str = "") -> Zip:
    item, rest = divmod(cover_id, ITEM_SIZE)
    return Zip(tier, f"{item:04d}", rest // BATCH_SIZE)


def parse_listing(html: str, z: Zip) -> set[int] | None:
    """The IDs a listing page holds, or None when the page was cut short."""
    if not LISTING_END.search(html):
        return None
    ids = {int(m) for m in LISTING_ENTRY.findall(html)}
    return {i for i in ids if z.first_id <= i < z.first_id + BATCH_SIZE}


def parse_zip_names(metadata: dict, tier: str, item: str) -> list[Zip]:
    pattern = re.compile(rf"{item_name(tier, item)}_(\d{{2}})\.zip")
    batches = sorted(int(m[1]) for f in metadata.get("files", []) if (m := pattern.fullmatch(f.get("name", ""))))
    return [Zip(tier, item, b) for b in batches]


def sample_missing(missing: list[int]) -> list[int]:
    if len(missing) <= SAMPLE_ALL_UPTO:
        return missing
    n = len(missing) - 1
    return sorted({missing[round(k * n / 4)] for k in range(5)})


def classify_pointer(cover_id: int, status: int, filename: str | None, z: Zip, listed: bool) -> str:
    """The verdict one cover ID gives for zip ``z``, which does not list it unless ``listed``."""
    if status == 404:
        return "short_no_record"
    if status != 200 or filename is None:
        return "indeterminate"
    if LOCAL_POINTER.fullmatch(filename):
        return "partial"
    m = ZIP_POINTER.fullmatch(filename)
    if not m or (m[1], int(m[2])) != (z.item, z.batch):
        return "indeterminate"
    return "ok" if listed else "LOSS"


def indeterminate_row(name: str, error: str) -> dict:
    return {"batch": name, "listing_count": 0, "verdict": "indeterminate", "evidence_ids": [], "error": error}


# Why a zip is expected. Only the first three are evidence that it existed.
EXPECTED_BY_EVIDENCE = ("known", "baseline", "pointer")
EXPECTED_BY_INFERENCE = "below_newest"


def missing_zip_row(z: Zip, expected_by: str) -> dict:
    return {"batch": z.name, "listing_count": 0, "verdict": "missing_zip", "evidence_ids": [], "expected_by": expected_by}


class Checker:
    def __init__(self, http: Http):
        self.http = http
        self._listings: dict[Zip, set[int] | None] = {}
        self._zips: dict[tuple[str, str], list[Zip]] = {}
        self._reread: dict[tuple[str, str], list[Zip] | None] = {}
        # Full-size zips that a cover's filename pointed into during this run.
        self.pointed: set[Zip] = set()

    def fetch_listing(self, z: Zip) -> set[int] | None:
        """The IDs the zip holds; None if the listing is unreadable or cut short."""
        try:
            r = self.http.get(z.listing_url)
            r.raise_for_status()
        except httpx.HTTPError:
            return None
        return parse_listing(r.text, z)

    def listing(self, z: Zip) -> set[int] | None:
        if z not in self._listings:
            self._listings[z] = self.fetch_listing(z)
        return self._listings[z]

    def pointer(self, cover_id: int) -> tuple[int, str | None]:
        """Return (HTTP status, filename). Nothing else from the body is kept."""
        try:
            r = self.http.get(f"https://covers.openlibrary.org/b/id/{cover_id}.json")
        except httpx.TransportError:
            return 0, None
        if r.status_code != 200:
            return r.status_code, None
        try:
            filename = r.json().get("filename")
        except ValueError:
            return r.status_code, None
        if not isinstance(filename, str):
            return 200, None
        if m := ZIP_POINTER.fullmatch(filename):
            self.pointed.add(Zip("", m[1], int(m[2])))
        return 200, filename

    def zips(self, tier: str, item: str) -> list[Zip]:
        """The item's zips; empty when archive.org has no such item or it lists none.

        A missing item answers 200 with ``{}``, so that is indistinguishable from
        an item that vanished, and callers must not read it as "zero covers".
        """
        if (tier, item) not in self._zips:
            r = self.http.get(f"https://archive.org/metadata/{item_name(tier, item)}")
            r.raise_for_status()
            self._zips[tier, item] = parse_zip_names(r.json(), tier, item)
        return self._zips[tier, item]

    def confirmed_missing(self, z: Zip) -> bool:
        """Re-read the item's metadata once, uncached: is the zip still absent?"""
        if (z.tier, z.item) not in self._reread:
            try:
                r = self.http.get(f"https://archive.org/metadata/{item_name(z.tier, z.item)}")
                r.raise_for_status()
                self._reread[z.tier, z.item] = parse_zip_names(r.json(), z.tier, z.item)
            except httpx.HTTPError:
                self._reread[z.tier, z.item] = None
        reread = self._reread[z.tier, z.item]
        return reread is not None and z not in reread

    def fetched_zips(self, tier: str, item: str) -> list[Zip] | None:
        """The item's zips if its metadata was already read this run; never a request."""
        return self._zips.get((tier, item))

    def id_verdict(self, cover_id: int, tier: str = "") -> str:
        z = zip_for_id(cover_id, tier)
        if not (listed := self.listing(z)):
            return "indeterminate"
        status, filename = self.pointer(cover_id)
        return classify_pointer(cover_id, status, filename, z, cover_id in listed)

    def check(self, z: Zip) -> dict:
        listed = self.listing(z)
        if listed is None:
            return indeterminate_row(z.name, "listing unreadable or cut short")
        if not listed:
            # An empty listing is what a changed listing format looks like.
            return indeterminate_row(z.name, "listing empty")
        missing = [i for i in range(z.first_id, z.first_id + BATCH_SIZE) if i not in listed]
        row: dict = {"batch": z.name, "listing_count": len(listed), "missing_count": len(missing), "sampled": 0}
        if not missing:
            return row | {"verdict": "ok", "evidence_ids": []}
        sample = sample_missing(missing)
        verdicts = {i: classify_pointer(i, *self.pointer(i), z, listed=False) for i in sample}
        worst = max(verdicts.values(), key=SEVERITY.index)
        evidence = [i for i, v in verdicts.items() if v == worst]
        row |= {"sampled": len(sample), "verdict": worst, "evidence_ids": evidence}
        if worst == "partial":
            row["serves"] = self.serves(evidence[0], z.tier.upper() or "L")
            if row["serves"] == 302:
                row["verdict"] = "LOSS"
        if row["verdict"] == "LOSS":
            reread = self.fetch_listing(z)
            if reread is None or len(reread) != len(listed):
                row |= {"verdict": "indeterminate", "error": "listing changed between two reads"}
        return row

    def serves(self, cover_id: int, size: str = "L") -> int | None:
        """HEAD status for the image. Without default=false a missing cover answers 200 with a placeholder."""
        try:
            return self.http.head(f"https://covers.openlibrary.org/b/id/{cover_id}-{size}.jpg?default=false").status_code
        except httpx.TransportError:
            return None

    def probe_above(self, top: Zip) -> None:
        """Read pointers in the batch above the newest zip until one has a record."""
        first = top.first_id + BATCH_SIZE
        for offset in ABOVE_TOP_OFFSETS:
            if self.pointer(first + offset)[0] == 200:
                return

    def newest_cover_id(self, floor: int) -> int:
        """Within NEWEST_ID_RESOLUTION of the newest cover ID, probing up from ``floor``, which exists.

        Robust to up to END_OF_IDS_TAIL - 1 consecutive deleted IDs; see newest_existing_id.
        """
        return newest_existing_id(lambda i: self.pointer(i)[0] == 200, floor, GALLOP_FIRST_STEP, NEWEST_ID_RESOLUTION, END_OF_IDS_TAIL, MAX_NEWEST_RESUMES)

    def open_batch_control(self, newest_zip: Zip) -> str | None:
        """None if a cover in the open batch is local and served; otherwise why not."""
        end = newest_zip.first_id + BATCH_SIZE - 1
        floors = range(end, end - FLOOR_CANDIDATES, -1)
        floor = next((i for i in floors if self.pointer(i)[0] == 200), None)
        if floor is None:
            return f"serves control: no cover at {floors[-1]}-{floors[0]}, the end of the newest zip's batch, to probe up from"
        try:
            newest = self.newest_cover_id(floor)
        except NewestIdNotFound as e:
            return f"serves control: newest cover ID not found above {floor}: {e}; probed {e.tried}"
        tried = []
        for k in range(1, OPEN_BATCH_CANDIDATES + 1):
            cover_id = newest - k * NEWEST_ID_RESOLUTION
            status, filename = self.pointer(cover_id)
            local = bool(filename and LOCAL_POINTER.fullmatch(filename))
            served = self.serves(cover_id) if local else None
            if served == 200:
                return None
            tried.append(f"{cover_id} (record {status}, local {local}, serves {served})")
        return f"serves control: no open-batch cover near {newest} is local and served: " + "; ".join(tried)


def known_loss_status(row: dict, expected: dict) -> str:
    """unchanged, grew or shrank; or failed when the known loss reads as something else."""
    if "missing_count" not in row:
        return "failed"  # unreadable listing: not evidence of a repair
    if row["missing_count"] < expected["missing_count"]:
        return "shrank"
    if row["verdict"] != "LOSS":
        return "failed"
    return "grew" if row["missing_count"] > expected["missing_count"] else "unchanged"


def controls(checker: Checker, known_rows: dict[str, dict], known: dict[str, dict], newest_zip: Zip) -> tuple[list[str], str]:
    """Return the failed controls and whether the positive control ran live or on the fixture only."""
    failures = []
    for name, row in known_rows.items():
        if known_loss_status(row, known[name]) == "failed":
            failures.append(
                f"known loss {name} read as {row['verdict']} with missing_count {row.get('missing_count')}, expected LOSS with {known[name]['missing_count']}"
            )
    positive = "live"
    if (v := checker.id_verdict(POSITIVE_CONTROL_ID)) != "LOSS":
        positive_row = known_rows.get(zip_for_id(POSITIVE_CONTROL_ID).name)
        if positive_row and positive_row["verdict"] != "LOSS" and known_loss_status(positive_row, known[positive_row["batch"]]) == "shrank":
            positive = "fixture_only"
        else:
            failures.append(f"positive control: cover {POSITIVE_CONTROL_ID} read as {v}, expected LOSS")
    if (v := checker.id_verdict(NEGATIVE_CONTROL_ID)) != "ok":
        failures.append(f"negative control: cover {NEGATIVE_CONTROL_ID} read as {v}, expected ok")
    if failure := checker.open_batch_control(newest_zip):
        failures.append(failure)
    if checker.serves(SERVES_ABSENT_ID) == 200:
        failures.append(f"serves control: absent cover {SERVES_ABSENT_ID} answered 200")
    return failures, positive


def load_known_losses(path: Path = KNOWN_LOSSES_FILE) -> dict[str, dict]:
    return {entry["batch"]: entry for entry in json.loads(path.read_text())}


def newest_zip(checker: Checker, start: str) -> Zip | None:
    """The newest full-size zip, in ``start`` or any later item that has zips."""
    found, n = None, int(start)
    while zips := checker.zips("", f"{n:04d}"):
        found, n = zips[-1], n + 1
    return found


def main_scope(checker: Checker, top: Zip, n: int) -> list[Zip | dict]:
    """The newest ``n`` full-size batch numbers, down from ``top``, across item boundaries."""
    top_index = int(top.item) * BATCHES_PER_ITEM + top.batch
    first = max(top_index - n + 1, int(FIRST_ZIP_ITEM) * BATCHES_PER_ITEM)
    out: list[Zip | dict] = []
    for index in range(first, top_index + 1):
        item_no, batch = divmod(index, BATCHES_PER_ITEM)
        item = f"{item_no:04d}"
        listed = checker.zips("", item)
        if not listed:
            if batch == 0 or index == first:
                out.append(indeterminate_row(item_name("", item), "item lists no zips"))
            continue
        z = Zip("", item, batch)
        out.append(z if z in listed else missing_zip_row(z, EXPECTED_BY_INFERENCE))
    return out


def item_scope(checker: Checker, tier: str, item: str) -> list[Zip | dict]:
    """Every zip of one item, with a row for each batch below its newest zip that is absent."""
    listed = checker.zips(tier, item)
    if not listed:
        return [indeterminate_row(item_name(tier, item), "item lists no zips")]
    present = {z.batch for z in listed}
    return [Zip(tier, item, b) if b in present else missing_zip_row(Zip(tier, item, b), EXPECTED_BY_INFERENCE) for b in range(max(present) + 1)]


@dataclass
class Tally:
    verdicts: Counter = field(default_factory=Counter)
    known: dict[str, str] = field(default_factory=dict)
    unknown_losses: int = 0
    inferred_missing: int = 0
    conditions: set[str] = field(default_factory=set)

    def add(self, row: dict, known: dict[str, dict]):
        name = row["batch"]
        if name in known and "missing_count" in row:
            self.known[name] = known_loss_status(row, known[name])
            row["known"] = self.known[name] == "unchanged"
        if row["verdict"] == "LOSS" and self.known.get(name) not in ("unchanged", "shrank"):
            self.unknown_losses += 1
        if row["verdict"] == "missing_zip":
            if row["expected_by"] in EXPECTED_BY_EVIDENCE:
                self.unknown_losses += 1
            else:
                self.inferred_missing += 1
        self.verdicts[row["verdict"]] += 1

    def exit_code(self) -> int:
        if "control" in self.conditions:
            return EXIT_CONTROL
        if self.unknown_losses:
            return EXIT_LOSS
        if "shrank" in self.known.values():
            return EXIT_STALE
        if "budget" in self.conditions:
            return EXIT_BUDGET
        if self.verdicts["indeterminate"] or self.inferred_missing or "error" in self.conditions:
            return EXIT_INDETERMINATE
        return EXIT_OK


def run(
    checker: Checker,
    items: list[str] | None,
    tiers: list[str],
    known: dict[str, dict],
    baseline: set[str] | None = None,
    main_batches: int = MAIN_BATCHES,
    out=sys.stdout,
    err=sys.stderr,
) -> int:
    tally = Tally()
    positive = "not run"
    printed: set[str] = set()

    def emit(row: dict):
        if row["verdict"] == "missing_zip" and not checker.confirmed_missing(zip_from_name(row["batch"])):
            row = indeterminate_row(row["batch"], "absence not confirmed by a second read of the item")
        if row["batch"] not in printed:
            printed.add(row["batch"])
            tally.add(row, known)
            print(json.dumps(row), file=out, flush=True)

    try:
        top = newest_zip(checker, DEFAULT_ITEM)
        known_rows = {name: checker.check(zip_from_name(name)) for name in known}
        failures = ["no full-size zip found to anchor the controls"]
        if top:
            failures, positive = controls(checker, known_rows, known, top)
        if failures:
            tally.conditions.add("control")
            for f in failures:
                print(json.dumps({"control_failed": f}), file=err)
        else:
            assert top is not None
            for name in sorted(known.keys() | (baseline or set())):
                named = zip_from_name(name)
                if named not in checker.zips(named.tier, named.item):
                    emit(missing_zip_row(named, "known" if name in known else "baseline"))
                else:
                    emit(known_rows.get(name) or checker.check(named))
            scope = main_scope(checker, top, main_batches) if not items else [z for item in items for tier in tiers for z in item_scope(checker, tier, item)]
            # An inferred missing zip is held back: a filename read later in the run may be evidence for it.
            inferred: list[dict] = []
            for z in scope:
                if isinstance(z, dict) and z.get("expected_by") == EXPECTED_BY_INFERENCE:
                    inferred.append(z)
                else:
                    emit(z if isinstance(z, dict) else known_rows.get(z.name) or checker.check(z))
            checker.probe_above(top)
            for z in sorted(checker.pointed, key=lambda z: z.name):
                listed = checker.fetched_zips(z.tier, z.item)
                if listed is not None and z not in listed:
                    emit(missing_zip_row(z, "pointer"))
            for row in inferred:
                emit(row)
    except BudgetExceeded as e:
        tally.conditions.add("budget")
        print(json.dumps({"budget_exceeded": str(e)}), file=err)
    except Exception as e:  # noqa: BLE001 -- a crash must not exit 1, which means LOSS
        tally.conditions.add("error")
        print(json.dumps({"error": type(e).__name__}), file=err)
    code = tally.exit_code()
    if tally.unknown_losses:
        tally.conditions.add("loss")
    if "shrank" in tally.known.values():
        tally.conditions.add("stale")
    summary = {
        "summary": dict(tally.verdicts),
        "conditions": sorted(tally.conditions),
        "known_losses": tally.known,
        "positive_control": positive,
        "requests": checker.http.count,
        "exit": code,
    }
    print(json.dumps(summary), file=err)
    return code


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--items", nargs="+", help="check these whole 4-digit items instead of the newest batches; needs --max-requests")
    p.add_argument("--tiers", nargs="+", default=[""], choices=TIERS, help='with --items: "" (full size, default), s, m, l')
    p.add_argument("--baseline", type=Path, help="JSON list of {batch} entries: zips that must exist")
    p.add_argument("--max-requests", type=int, help=f"default {DEFAULT_MAX_REQUESTS}; required with --items")
    p.add_argument("--delay", type=float, default=1.0, help="seconds between requests")
    args = p.parse_args(argv)
    if args.items and args.max_requests is None:
        p.error("--items is the census path and needs its own --max-requests (about 3000)")
    try:
        known = load_known_losses()
        baseline = {e["batch"] for e in json.loads(args.baseline.read_text())} if args.baseline else set()
        for name in known.keys() | baseline:
            zip_from_name(name)
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(json.dumps({"error": f"known-loss or baseline file unreadable: {type(e).__name__}"}), file=sys.stderr)
        return EXIT_CONTROL
    http = Http(args.max_requests or DEFAULT_MAX_REQUESTS, args.delay)
    return run(Checker(http), args.items, args.tiers, known, baseline)


if __name__ == "__main__":
    sys.exit(main())
