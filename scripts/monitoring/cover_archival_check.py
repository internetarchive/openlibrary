"""Find covers whose record points into an archive.org zip that does not hold them.

That state is what lost covers 14,624,073-14,629,999 from ``covers_0014_62``
(#9836): the batch was zipped and uploaded while still open, then finalized by a
later run, so its later covers now redirect into a zip that holds only 4,073.
A short zip alone is ordinary, and so is a finalized batch; only the pairing is
a loss, and both halves are public:

- archive.org's listing of each zip says what the zip holds;
- ``covers.openlibrary.org/b/id/<id>.json`` has a ``filename`` field that is
  either a local path or the zip the cover redirects into.

For every zip, count its listing. For each zip short of ``BATCH_SIZE``, read
``filename`` for its missing IDs (all of them when there are at most
``SAMPLE_ALL_UPTO``, otherwise the first, the last and three evenly spaced) and
classify the batch by the worst one:

- ``ok``: the zip holds the whole batch;
- ``short_no_record``: every sampled missing ID is a 404, so no pointer can break;
- ``partial``: a missing ID still points at a local file (a partial upload, the
  loss's precondition; known to happen for covers that failed to archive).
  ``serves`` is the status of a HEAD on one such cover's ``-L.jpg?default=false``:
  only 200 means it is still served locally, with no archived copy. A 302 means
  the cover redirects into the zip after all (the redirect is gated on the row's
  ``uploaded`` flag, not on ``filename``), so the batch is reported as LOSS;
- ``LOSS``: a missing ID points at this very zip;
- ``indeterminate``: anything else (another zip, an unknown filename shape, a
  failed request, an empty listing). Never read as either verdict. An item that
  lists no zips gets one such row named for the item, with ``error``: archive.org
  answers a missing item with 200 and ``{}``, which must not read as zero covers.

Known losses are listed with their evidence in ``cover_archival_known_losses.json``.
Each is checked on every run, whatever the scope, and reported as ``known``
while its ``missing_count`` is unchanged. One that grows is a new loss; one that
shrinks has been at least partly repaired and the file needs updating.

The controls run first, and no verdict is printed unless all pass:

- positive: cover 14627720 reads as LOSS. Once ``covers_0014_62`` is repaired
  there is no live positive case, and the summary says ``positive_control:
  fixture_only``: from then on only the recorded test fixture exercises it;
- negative: cover 14615000 points at ``covers_0014_61.zip`` and is listed in it;
- ``serves``: a present local cover answers 200 and a missing one does not;
- every known loss still reads as LOSS, or has shrunk.

Only ``id`` and ``filename`` are kept from each ``/b/id/<id>.json`` response
(data minimisation). Raw bodies are never logged or stored.

Each run checks the full-size zips of the newest item(s), plus one rotated
window of ``--rotate-zips`` zips from the other items and sizes, chosen by ISO
week, so every zip is eventually covered within the request cap.

Output: one JSON line per zip on stdout, ``{batch, listing_count,
missing_count, sampled, verdict, evidence_ids}`` plus ``serves`` on partial
rows and ``known`` on allowlisted ones, then a summary line on stderr with no
``batch`` key. Exit codes, most urgent first when several apply:

- 2: a control failed; no verdicts printed;
- 4: request cap reached; the rows printed so far are not a census;
- 1: a LOSS not on the known-loss list, or a known loss that grew;
- 5: a known loss shrank, so the list is stale;
- 3: indeterminate, including any unexpected error;
- 0: clean.

Usage:
    python scripts/monitoring/cover_archival_check.py
    python scripts/monitoring/cover_archival_check.py --items 0014 --tiers "" l
"""

import argparse
import json
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx

BATCH_SIZE = 10_000
ITEM_SIZE = 1_000_000
TIERS = ("", "s", "m", "l")
DEFAULT_ITEM = "0014"
FIRST_ZIP_ITEM = "0008"  # code.py redirects only IDs >= 8,000,000 into zips
SAMPLE_ALL_UPTO = 6
DEFAULT_ROTATE_ZIPS = 30
UA = "openlibrary-cover-archival-check/1.0 (+https://github.com/internetarchive/openlibrary/issues/13762)"

KNOWN_LOSSES_FILE = Path(__file__).with_name("cover_archival_known_losses.json")

POSITIVE_CONTROL_ID = 14627720
NEGATIVE_CONTROL_ID = 14615000
SERVES_PRESENT_ID = 15000000
SERVES_ABSENT_ID = 999999999

EXIT_OK, EXIT_LOSS, EXIT_CONTROL, EXIT_INDETERMINATE, EXIT_BUDGET, EXIT_STALE = 0, 1, 2, 3, 4, 5

ZIP_NAME = re.compile(r"(?:([sml])_)?covers_(\d{4})_(\d{2})")
ZIP_POINTER = re.compile(r"covers_(\d{4})/covers_\1_(\d{2})\.zip")
LOCAL_POINTER = re.compile(r"\d{4}/\d{2}/\d{2}/[^/]+\.jpg")
LISTING_ENTRY = re.compile(r"(\d{10})(?:-[SML])?\.jpg")

# Verdict precedence: the worst sampled ID decides the batch.
SEVERITY = ["ok", "short_no_record", "partial", "indeterminate", "LOSS"]


class BudgetExceeded(Exception):
    pass


class Http:
    """GETs with a hard request cap, a delay between requests and an identifying UA."""

    def __init__(self, max_requests: int = 100, delay: float = 1.0, client: httpx.Client | None = None):
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
        prefix = f"{self.tier}_" if self.tier else ""
        return f"{prefix}covers_{self.item}_{self.batch:02d}"

    @property
    def first_id(self) -> int:
        return int(self.item) * ITEM_SIZE + self.batch * BATCH_SIZE

    @property
    def listing_url(self) -> str:
        prefix = f"{self.tier}_" if self.tier else ""
        return f"https://archive.org/download/{prefix}covers_{self.item}/{self.name}.zip/"


def zip_from_name(name: str) -> Zip:
    m = ZIP_NAME.fullmatch(name)
    if not m:
        raise ValueError(f"not a zip batch name: {name!r}")
    return Zip(m[1] or "", m[2], int(m[3]))


def zip_for_id(cover_id: int, tier: str = "") -> Zip:
    item, rest = divmod(cover_id, ITEM_SIZE)
    return Zip(tier, f"{item:04d}", rest // BATCH_SIZE)


def parse_listing(html: str, z: Zip) -> set[int]:
    ids = {int(m) for m in LISTING_ENTRY.findall(html)}
    return {i for i in ids if z.first_id <= i < z.first_id + BATCH_SIZE}


def parse_zip_names(metadata: dict, tier: str, item: str) -> list[Zip]:
    prefix = f"{tier}_" if tier else ""
    pattern = re.compile(rf"{prefix}covers_{item}_(\d{{2}})\.zip")
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


class Checker:
    def __init__(self, http: Http):
        self.http = http
        self._listings: dict[Zip, set[int]] = {}
        self._zips: dict[tuple[str, str], list[Zip]] = {}

    def listing(self, z: Zip) -> set[int]:
        """The IDs the zip holds; empty if the listing could not be read."""
        if z not in self._listings:
            try:
                r = self.http.get(z.listing_url)
                r.raise_for_status()
                self._listings[z] = parse_listing(r.text, z)
            except httpx.HTTPError:
                self._listings[z] = set()
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
        return 200, filename if isinstance(filename, str) else None

    def zips(self, tier: str, item: str) -> list[Zip]:
        """The item's zips; empty when archive.org has no such item or it lists none.

        A missing item answers 200 with ``{}``, so that is indistinguishable from
        an item that vanished, and callers must not read it as "zero covers".
        """
        if (tier, item) not in self._zips:
            prefix = f"{tier}_" if tier else ""
            r = self.http.get(f"https://archive.org/metadata/{prefix}covers_{item}")
            r.raise_for_status()
            self._zips[tier, item] = parse_zip_names(r.json(), tier, item)
        return self._zips[tier, item]

    def item_zips(self, tier: str, item: str) -> list[Zip] | str:
        """The item's zips, or the item's name when it lists none where zips are expected."""
        return self.zips(tier, item) or f"{tier}_covers_{item}".lstrip("_")

    def id_verdict(self, cover_id: int, tier: str = "") -> str:
        z = zip_for_id(cover_id, tier)
        if not (listed := self.listing(z)):
            return "indeterminate"
        status, filename = self.pointer(cover_id)
        return classify_pointer(cover_id, status, filename, z, cover_id in listed)

    def check(self, z: Zip) -> dict:
        listed = self.listing(z)
        if not listed:
            # An unreadable listing, or an empty one, which is what a changed listing format looks like.
            return {"batch": z.name, "listing_count": 0, "verdict": "indeterminate", "evidence_ids": []}
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
        return row

    def serves(self, cover_id: int, size: str = "L") -> int | None:
        """HEAD status for the image. Without default=false a missing cover answers 200 with a placeholder."""
        try:
            return self.http.head(f"https://covers.openlibrary.org/b/id/{cover_id}-{size}.jpg?default=false").status_code
        except httpx.TransportError:
            return None


def known_loss_status(row: dict, expected: dict) -> str:
    """unchanged, grew or shrank; or failed when the known loss reads as something else."""
    if "missing_count" not in row:
        return "failed"  # unreadable listing: not evidence of a repair
    if row["missing_count"] < expected["missing_count"]:
        return "shrank"
    if row["verdict"] != "LOSS":
        return "failed"
    return "grew" if row["missing_count"] > expected["missing_count"] else "unchanged"


def controls(checker: Checker, known_rows: dict[str, dict], known: dict[str, dict]) -> tuple[list[str], str]:
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
    if (status := checker.serves(SERVES_PRESENT_ID)) != 200:
        failures.append(f"serves control: present cover {SERVES_PRESENT_ID} answered {status}, expected 200")
    if (status := checker.serves(SERVES_ABSENT_ID)) == 200:
        failures.append(f"serves control: absent cover {SERVES_ABSENT_ID} answered 200")
    return failures, positive


def load_known_losses(path: Path = KNOWN_LOSSES_FILE) -> dict[str, dict]:
    return {entry["batch"]: entry for entry in json.loads(path.read_text())}


def discover_items(checker: Checker, start: str) -> list[str]:
    """The start item plus every later one that already holds full-size zips."""
    items: list[str] = []
    n = int(start)
    while checker.zips("", f"{n:04d}") or not items:
        items.append(f"{n:04d}")
        n += 1
    return items


def rotation_slots(newest: list[str], window: int) -> list[tuple[str, str, int]]:
    """Every (tier, item, first batch) window outside the default full-size pass."""
    slots: list[tuple[str, str, int]] = []
    for item_no in range(int(FIRST_ZIP_ITEM), int(newest[-1]) + 1):
        item = f"{item_no:04d}"
        for tier in TIERS:
            if tier == "" and item in newest:
                continue
            slots.extend((tier, item, start) for start in range(0, ITEM_SIZE // BATCH_SIZE, window))
    return slots


def rotated_zips(checker: Checker, newest: list[str], window: int, today: date) -> list[Zip] | str:
    slots = rotation_slots(newest, window)
    week = today.toordinal() // 7
    tier, item, start = slots[week % len(slots)]
    zips = checker.item_zips(tier, item)
    if isinstance(zips, str):
        return zips
    return [z for z in zips if start <= z.batch < start + window]


def unlisted_item_row(name: str) -> dict:
    return {"batch": name, "listing_count": 0, "verdict": "indeterminate", "evidence_ids": [], "error": "item lists no zips"}


def run(
    checker: Checker,
    items: list[str] | None,
    tiers: list[str],
    known: dict[str, dict],
    rotate_zips: int = DEFAULT_ROTATE_ZIPS,
    today: date | None = None,
    out=sys.stdout,
    err=sys.stderr,
) -> int:
    try:
        known_rows = {name: checker.check(zip_from_name(name)) for name in known}
        failures, positive = controls(checker, known_rows, known)
        if failures:
            for f in failures:
                print(json.dumps({"control_failed": f}), file=err)
            print("# controls failed; no verdicts issued", file=err)
            return EXIT_CONTROL
        items = items or discover_items(checker, DEFAULT_ITEM)
        scope = [checker.item_zips(tier, item) for item in items for tier in tiers]
        if rotate_zips:
            scope.append(rotated_zips(checker, items, rotate_zips, today or date.today()))
        scope.append([zip_from_name(name) for name in known])
        verdicts: Counter = Counter()
        statuses: dict[str, str] = {}
        unknown_losses = 0
        for z in dict.fromkeys(z for part in scope for z in ([part] if isinstance(part, str) else part)):
            if isinstance(z, str):
                row = unlisted_item_row(z)
                verdicts[row["verdict"]] += 1
                print(json.dumps(row), file=out, flush=True)
                continue
            row = known_rows.get(z.name) or checker.check(z)
            if z.name in known:
                statuses[z.name] = known_loss_status(row, known[z.name])
                row["known"] = statuses[z.name] == "unchanged"
            if row["verdict"] == "LOSS" and statuses.get(z.name) not in ("unchanged", "shrank"):
                unknown_losses += 1
            verdicts[row["verdict"]] += 1
            print(json.dumps(row), file=out, flush=True)
    except BudgetExceeded as e:
        print(json.dumps({"budget_exceeded": str(e)}), file=err)
        print("# request cap reached; the run is incomplete and its rows are not a census", file=err)
        return EXIT_BUDGET
    except Exception as e:  # noqa: BLE001 -- a crash must not exit 1, which means LOSS
        print(json.dumps({"error": type(e).__name__}), file=err)
        return EXIT_INDETERMINATE
    if unknown_losses:
        code = EXIT_LOSS
    elif "shrank" in statuses.values():
        code = EXIT_STALE
    elif verdicts["indeterminate"]:
        code = EXIT_INDETERMINATE
    else:
        code = EXIT_OK
    summary = {
        "summary": dict(verdicts),
        "known_losses": statuses,
        "positive_control": positive,
        "requests": checker.http.count,
        "exit": code,
    }
    print(json.dumps(summary), file=err)
    return code


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--items", nargs="+", help=f"4-digit item ids; default {DEFAULT_ITEM} and any later item with zips")
    p.add_argument("--tiers", nargs="+", default=[""], choices=TIERS, help='"" (full size, default), s, m, l')
    p.add_argument("--max-requests", type=int, default=150)
    p.add_argument("--rotate-zips", type=int, default=DEFAULT_ROTATE_ZIPS, help="size of the rotated window; 0 disables it")
    p.add_argument("--delay", type=float, default=1.0, help="seconds between requests")
    args = p.parse_args(argv)
    try:
        known = load_known_losses()
    except (OSError, ValueError, KeyError) as e:
        print(json.dumps({"error": f"known-loss list unreadable: {type(e).__name__}"}), file=sys.stderr)
        return EXIT_CONTROL
    return run(Checker(Http(args.max_requests, args.delay)), args.items, args.tiers, known, args.rotate_zips)


if __name__ == "__main__":
    sys.exit(main())
