import io
import json
from collections import Counter
from pathlib import Path

import httpx
import pytest

from scripts.monitoring.cover_archival_check import (
    EXIT_BUDGET,
    EXIT_CONTROL,
    EXIT_INDETERMINATE,
    EXIT_LOSS,
    EXIT_OK,
    EXIT_STALE,
    NEGATIVE_CONTROL_ID,
    POSITIVE_CONTROL_ID,
    SERVES_ABSENT_ID,
    Checker,
    Http,
    Zip,
    classify_pointer,
    load_known_losses,
    main,
    run,
    sample_missing,
)

FIXTURES = json.loads((Path(__file__).parent / "cover_archival_fixtures.json").read_text())
HEADER_LINE, ROW, *FOOTER_LINES = FIXTURES["listing_page_lines"]
KNOWN = load_known_losses()
RECORDED_POINTERS = {p["id"]: p for p in FIXTURES["pointers"]}
# Synthetic, not recorded: the newest cover ID the fake serves, so everything
# between the newest zip and here is backlog plus the open batch.
NEWEST_COVER = 15_260_000
LOCAL = "2024/09/01/OL1M-synthetic.jpg"


def listing_page(zip_name: str, first: int, last: int, complete: bool = True) -> str:
    """Rebuild a listing page from its recorded ID range and the verbatim lines of the real page."""
    rows = [ROW.replace("covers_0014_62.zip", f"{zip_name}.zip").replace("0014620000", f"{i:010d}") for i in range(first, last + 1)]
    return "\n".join([HEADER_LINE, *rows, *(FOOTER_LINES if complete else [])])


def full(item: str, batch: int) -> list[int]:
    first = int(item) * 1_000_000 + batch * 10_000
    return [first, first + 9_999]


class FakeServer:
    """archive.org and covers.openlibrary.org, served from recorded fixtures plus the overrides a test names."""

    def __init__(
        self,
        listings=None,
        pointers=None,
        zips=None,
        heads=None,
        truncated=(),
        second_listing=None,
        second_metadata=None,
        raise_on=(),
        unreachable=(),
    ):
        self.listings = dict(FIXTURES["listings"]) if listings is None else dict(listings)
        self.pointers = RECORDED_POINTERS | (pointers or {})
        self.zips = zips if zips is not None else {"covers_0014": sorted(n for n in self.listings if n.startswith("covers_0014_"))}
        self.heads = {h["id"]: h["status"] for h in FIXTURES["heads"]} | (heads or {})
        self.truncated = set(truncated)
        self.second_listing = second_listing or {}
        self.second_metadata = second_metadata or {}
        self.raise_on = set(raise_on)
        self.unreachable = set(unreachable)
        self.reads: Counter = Counter()

    def filename(self, cover_id: int) -> str | None:
        if cover_id in self.pointers:  # None: no record
            return (self.pointers[cover_id] or {}).get("filename")
        for name, (first, last) in self.listings.items():
            if name.startswith("covers_") and first <= cover_id <= last:
                return f"{name.rsplit('_', 1)[0]}/{name}.zip"
        tops = [last for name, (_, last) in self.listings.items() if name.startswith("covers_")]
        if tops and max(tops) < cover_id <= NEWEST_COVER:
            return LOCAL
        return None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.reads[url] += 1
        if any(s in url for s in self.raise_on):
            raise ValueError("injected")
        if url.startswith("https://archive.org/metadata/"):
            item = url.rsplit("/", 1)[1]
            if item not in self.zips:
                return httpx.Response(200, json=FIXTURES["missing_item_metadata"])
            names = self.second_metadata[item] if item in self.second_metadata and self.reads[url] > 1 else self.zips[item]
            if names is None:
                return httpx.Response(500)
            return httpx.Response(200, json={"files": [{"name": f"{n}.zip"} for n in names]})
        if url.startswith("https://archive.org/download/"):
            name = url.rstrip("/").rsplit("/", 1)[1].removesuffix(".zip")
            span = self.second_listing[name] if name in self.second_listing and self.reads[url] > 1 else self.listings.get(name)
            if span is None:
                return httpx.Response(404)
            first, last = span
            return httpx.Response(200, text=listing_page(name, first, last, complete=name not in self.truncated))
        cover_id = int(request.url.path.rsplit("/", 1)[1].split("-")[0].removesuffix(".json"))
        if cover_id in self.unreachable:
            raise httpx.ConnectError("injected")
        if request.method == "HEAD":
            status = self.heads.get(cover_id, 200 if self.filename(cover_id) else 404)
            if status == 404 and request.url.params.get("default") != "false":
                return httpx.Response(200, headers={"Content-Type": "image/gif"})  # the placeholder
            return httpx.Response(status)
        filename = self.filename(cover_id)
        if filename is None:
            return httpx.Response(404)
        return httpx.Response(200, json={"id": cover_id, "filename": filename})


def make_http(server: FakeServer | None = None, max_requests: int = 10_000) -> Http:
    return Http(max_requests=max_requests, delay=0, client=httpx.Client(transport=httpx.MockTransport(server or FakeServer())))


def run_to_strings(server=None, known=None, items=None, baseline=None, main_batches=2, max_requests=10_000, checker_cls=Checker):
    out, err = io.StringIO(), io.StringIO()
    code = run(
        checker_cls(make_http(server, max_requests)),
        items,
        [""],
        {} if known is None else known,
        baseline,
        main_batches=main_batches,
        out=out,
        err=err,
    )
    return code, [json.loads(r) for r in out.getvalue().splitlines()], err.getvalue().splitlines()


def summary(err: list[str]) -> dict:
    last = json.loads(err[-1])
    assert "batch" not in last
    return last


def missing_zips(rows: list[dict]) -> list[tuple[str, str]]:
    return [(r["batch"], r["expected_by"]) for r in rows if r["verdict"] == "missing_zip"]


# Fixtures and the recorded controls


def test_fixtures_hold_only_id_and_filename():
    assert all(set(p) == {"id", "filename"} for p in FIXTURES["pointers"])


def test_known_losses_file_names_batch_62_with_its_evidence():
    assert KNOWN["covers_0014_62"]["missing_count"] == 5927
    assert POSITIVE_CONTROL_ID in KNOWN["covers_0014_62"]["evidence_ids"]


def test_positive_control_batch_62_reads_as_loss():
    checker = Checker(make_http())
    assert checker.id_verdict(POSITIVE_CONTROL_ID) == "LOSS"
    assert checker.check(Zip("", "0014", 62)) == {
        "batch": "covers_0014_62",
        "listing_count": 4073,
        "missing_count": 5927,
        "sampled": 5,
        "verdict": "LOSS",
        "evidence_ids": [14624073, 14628517, 14629999],
    }


def test_negative_control_full_batch_61_reads_as_ok():
    checker = Checker(make_http())
    assert checker.id_verdict(NEGATIVE_CONTROL_ID) == "ok"
    row = checker.check(Zip("", "0014", 61))
    assert (row["listing_count"], row["verdict"]) == (10_000, "ok")


def test_each_listed_cover_counts_once_though_its_row_names_it_twice():
    assert Checker(make_http()).listing(Zip("", "0014", 62)) == set(range(14620000, 14624073))


# Classifying one batch


@pytest.mark.parametrize(
    ("status", "filename", "listed", "expected"),
    [
        (200, "covers_0014/covers_0014_62.zip", False, "LOSS"),
        (200, "covers_0014/covers_0014_62.zip", True, "ok"),
        (200, "2024/05/13/OL51693473M-JPnWV.jpg", False, "partial"),
        (404, None, False, "short_no_record"),
        (200, "covers_0014/covers_0014_61.zip", False, "indeterminate"),
        (200, "somewhere/else.png", False, "indeterminate"),
        (200, None, False, "indeterminate"),
        (503, None, False, "indeterminate"),
        (0, None, False, "indeterminate"),
    ],
)
def test_classify_pointer(status, filename, listed, expected):
    assert classify_pointer(14627720, status, filename, Zip("", "0014", 62), listed) == expected


def test_sample_missing_takes_all_of_a_small_gap_and_five_of_a_large_one():
    assert sample_missing([1, 2, 3, 4, 5, 6]) == [1, 2, 3, 4, 5, 6]
    assert sample_missing(list(range(100, 201))) == [100, 125, 150, 175, 200]


def batch_26(filename: str | None, **kwargs) -> FakeServer:
    """Batch 26, missing one ID whose record says ``filename`` (or has no record)."""
    listings = {"covers_0014_26": [14260000, 14269998]}
    pointers = {14269999: {"id": 14269999, "filename": filename} if filename else None}
    return FakeServer(listings, pointers, **kwargs)


def test_partial_row_records_whether_the_local_copy_still_serves():
    row = Checker(make_http(batch_26("2023/04/21/OL47642877M-X0Chl.jpg"))).check(Zip("", "0014", 26))
    assert (row["verdict"], row["serves"], row["evidence_ids"]) == ("partial", 200, [14269999])


def test_partial_that_actually_redirects_is_loss():
    server = batch_26("2023/04/21/OL47642877M-X0Chl.jpg", heads={14269999: 302})
    row = Checker(make_http(server)).check(Zip("", "0014", 26))
    assert (row["verdict"], row["serves"]) == ("LOSS", 302)


def test_missing_ids_without_records_are_not_loss():
    row = Checker(make_http(batch_26(None))).check(Zip("", "0014", 26))
    assert row["verdict"] == "short_no_record"
    assert "serves" not in row


def test_a_network_failure_on_a_pointer_is_indeterminate_not_no_record():
    row = Checker(make_http(batch_26(None, unreachable={14269999}))).check(Zip("", "0014", 26))
    assert row["verdict"] == "indeterminate"


def test_an_empty_listing_is_indeterminate_not_a_short_batch():
    row = Checker(make_http(FakeServer({"covers_0014_61": [1, 0]}))).check(Zip("", "0014", 61))
    assert row["verdict"] == "indeterminate"


def test_a_listing_cut_short_is_indeterminate_never_loss():
    listings = {"covers_0014_61": [14610000, 14612999]}  # 3,000 of 10,000, and no closing tags
    row = Checker(make_http(FakeServer(listings, truncated={"covers_0014_61"}))).check(Zip("", "0014", 61))
    assert row["verdict"] == "indeterminate"


def test_a_loss_whose_listing_changes_on_the_second_read_is_indeterminate():
    server = FakeServer(second_listing={"covers_0014_62": [14620000, 14629999]})
    row = Checker(make_http(server)).check(Zip("", "0014", 62))
    assert (row["verdict"], row["error"]) == ("indeterminate", "listing changed between two reads")


def test_serves_asks_for_no_placeholder():
    assert Checker(make_http()).serves(SERVES_ABSENT_ID) == 404


# Whole runs: controls, known losses, exit codes


def test_run_reports_loss_with_all_controls_passing():
    code, rows, err = run_to_strings()
    assert code == EXIT_LOSS
    assert [(r["batch"], r["verdict"]) for r in rows] == [("covers_0014_61", "ok"), ("covers_0014_62", "LOSS")]
    s = summary(err)
    assert (s["summary"], s["conditions"], s["positive_control"]) == ({"ok": 1, "LOSS": 1}, ["loss"], "live")


def test_a_known_loss_is_reported_but_does_not_alert():
    code, rows, err = run_to_strings(known=KNOWN)
    assert code == EXIT_OK
    assert [r["known"] for r in rows if r["batch"] == "covers_0014_62"] == [True]
    assert summary(err)["known_losses"] == {"covers_0014_62": "unchanged"}


def test_a_known_loss_is_checked_even_outside_the_scope():
    listings = FIXTURES["listings"] | {"covers_0013_00": full("0013", 0)}
    zips = {"covers_0013": ["covers_0013_00"], "covers_0014": ["covers_0014_61", "covers_0014_62"]}
    code, rows, _ = run_to_strings(FakeServer(listings, zips=zips), known=KNOWN, items=["0013"])
    assert code == EXIT_OK
    assert sorted(r["batch"] for r in rows) == ["covers_0013_00", "covers_0014_62"]


def with_expected_missing(n: int) -> dict:
    return {"covers_0014_62": KNOWN["covers_0014_62"] | {"missing_count": n}}


def test_a_known_loss_that_grew_is_a_new_loss():
    code, _, err = run_to_strings(known=with_expected_missing(5000))
    assert code == EXIT_LOSS
    assert summary(err)["known_losses"] == {"covers_0014_62": "grew"}


def test_a_known_loss_that_shrank_marks_the_list_stale():
    code, _, err = run_to_strings(known=with_expected_missing(6000))
    assert code == EXIT_STALE
    assert summary(err)["conditions"] == ["stale"]


def test_a_repaired_positive_case_leaves_the_control_on_the_fixture_only():
    listings = FIXTURES["listings"] | {"covers_0014_62": [14620000, 14629999]}
    code, _, err = run_to_strings(FakeServer(listings), known=KNOWN)
    assert code == EXIT_STALE
    s = summary(err)
    assert (s["positive_control"], s["known_losses"]) == ("fixture_only", {"covers_0014_62": "shrank"})


def test_a_known_loss_that_reads_as_something_else_fails_the_controls():
    pointers = {i: {"id": i, "filename": "covers_0014/covers_0014_61.zip"} for i in (14624073, 14628517, 14629999)}
    code, rows, err = run_to_strings(FakeServer(pointers=pointers), known=KNOWN)
    assert (code, rows) == (EXIT_CONTROL, [])
    assert any("known loss covers_0014_62" in line for line in err)
    assert summary(err)["exit"] == EXIT_CONTROL


def test_an_unreadable_known_loss_listing_is_a_control_failure_not_a_repair():
    listings = {"covers_0014_61": FIXTURES["listings"]["covers_0014_61"]}
    server = FakeServer(listings, zips={"covers_0014": ["covers_0014_61", "covers_0014_62"]})
    code, rows, _ = run_to_strings(server, known=KNOWN)
    assert (code, rows) == (EXIT_CONTROL, [])


def test_the_positive_control_fails_on_an_unreadable_listing():
    checker = Checker(make_http(FakeServer({"covers_0014_61": FIXTURES["listings"]["covers_0014_61"]})))
    assert checker.id_verdict(POSITIVE_CONTROL_ID) == "indeterminate"


@pytest.mark.parametrize("broken_id", [POSITIVE_CONTROL_ID, NEGATIVE_CONTROL_ID], ids=["positive", "negative"])
def test_the_controls_run_whatever_the_scope(broken_id):
    listings = FIXTURES["listings"] | {"covers_0013_00": full("0013", 0)}
    zips = {"covers_0013": ["covers_0013_00"], "covers_0014": ["covers_0014_61", "covers_0014_62"]}
    server = FakeServer(listings, {broken_id: {"id": broken_id, "filename": LOCAL}}, zips=zips)
    code, rows, _ = run_to_strings(server, items=["0013"])
    assert (code, rows) == (EXIT_CONTROL, [])


def test_the_absent_serves_control_must_not_answer_200():
    code, rows, err = run_to_strings(FakeServer(heads={SERVES_ABSENT_ID: 200}))
    assert (code, rows) == (EXIT_CONTROL, [])
    assert any(f"absent cover {SERVES_ABSENT_ID}" in line for line in err)


def test_the_open_batch_control_uses_covers_above_the_newest_zip():
    checker = Checker(make_http())
    assert NEWEST_COVER - 100 <= checker.newest_cover_id(14629999) <= NEWEST_COVER
    assert checker.open_batch_control(Zip("", "0014", 62)) is None


def test_the_open_batch_control_names_what_it_tried():
    checker = Checker(make_http())
    newest = checker.newest_cover_id(14629999)
    candidates = [newest - k * 100 for k in range(1, 4)]
    code, rows, err = run_to_strings(FakeServer(heads=dict.fromkeys(candidates, 404)))
    assert (code, rows) == (EXIT_CONTROL, [])
    failure = next(json.loads(line)["control_failed"] for line in err if "open-batch" in line)
    assert all(str(i) in failure for i in candidates)


def test_the_open_batch_control_fails_without_a_cover_to_probe_up_from():
    server = FakeServer(pointers=dict.fromkeys(range(14629995, 14630000)))
    assert "to probe up from" in Checker(make_http(server)).open_batch_control(Zip("", "0014", 62))


def test_one_deleted_cover_at_the_end_of_the_newest_zip_does_not_fail_the_control():
    server = FakeServer(pointers={14629999: None})
    assert Checker(make_http(server)).open_batch_control(Zip("", "0014", 62)) is None


def test_the_open_batch_control_needs_a_local_filename_not_just_a_served_image():
    newest = Checker(make_http()).newest_cover_id(14629999)
    candidates = [newest - k * 100 for k in range(1, 4)]
    zipped = {i: {"id": i, "filename": "covers_0015/covers_0015_26.zip"} for i in candidates}
    failure = Checker(make_http(FakeServer(pointers=zipped))).open_batch_control(Zip("", "0014", 62))
    assert failure is not None
    assert "local False" in failure


def test_no_zips_anywhere_fails_the_controls_rather_than_reading_as_empty():
    code, rows, _ = run_to_strings(FakeServer(zips={}))
    assert (code, rows) == (EXIT_CONTROL, [])


def test_indeterminate_exits_non_zero():
    pointers = {i: {"id": i, "filename": "covers_0014/covers_0014_61.zip"} for i in (14624073, 14625555, 14627036, 14628517, 14629999)}
    code, _, _ = run_to_strings(FakeServer(pointers=pointers))
    assert code == EXIT_INDETERMINATE


def test_an_unreadable_listing_is_indeterminate_not_a_crash():
    zips = {"covers_0014": ["covers_0014_61", "covers_0014_62", "covers_0014_63"]}
    code, rows, _ = run_to_strings(FakeServer(zips=zips), known=KNOWN, main_batches=3)
    assert code == EXIT_INDETERMINATE
    assert rows[-1] == {
        "batch": "covers_0014_63",
        "listing_count": 0,
        "verdict": "indeterminate",
        "evidence_ids": [],
        "error": "listing unreadable or cut short",
    }


def test_an_unexpected_error_is_indeterminate_never_the_loss_exit():
    code, rows, err = run_to_strings(FakeServer(zips={"covers_0014": None}))
    assert (code, rows) == (EXIT_INDETERMINATE, [])
    assert json.loads(err[0]) == {"error": "HTTPStatusError"}
    assert summary(err)["conditions"] == ["error"]


def test_hitting_the_request_cap_fails_loudly_with_a_summary():
    code, rows, err = run_to_strings(max_requests=5)
    assert (code, rows) == (EXIT_BUDGET, [])
    assert "budget_exceeded" in err[0]
    assert summary(err)["conditions"] == ["budget"]


def new_loss_in_batch_60(**kwargs) -> FakeServer:
    """A new tail-shaped loss in batch 60, which the main scope reaches before batches 61-63."""
    listings = FIXTURES["listings"] | {"covers_0014_60": [14600000, 14604999], "covers_0014_63": full("0014", 63)}
    pointers = {i: {"id": i, "filename": "covers_0014/covers_0014_60.zip"} for i in sample_missing(list(range(14605000, 14610000)))}
    return FakeServer(listings, pointers, **kwargs)


def test_a_printed_loss_outranks_a_later_crash():
    server = new_loss_in_batch_60(raise_on={"covers_0014_63.zip/"})
    code, rows, err = run_to_strings(server, known=KNOWN, main_batches=4)
    assert [r["verdict"] for r in rows if r["batch"] == "covers_0014_60"] == ["LOSS"]
    assert "covers_0014_63" not in [r["batch"] for r in rows]
    assert code == EXIT_LOSS
    assert summary(err)["conditions"] == ["error", "loss"]


def test_a_printed_loss_outranks_a_later_budget_stop():
    outcomes = set()
    for cap in range(1, 120):
        code, rows, err = run_to_strings(new_loss_in_batch_60(), known=KNOWN, main_batches=4, max_requests=cap)
        loss_printed = any(r["batch"] == "covers_0014_60" and r["verdict"] == "LOSS" for r in rows)
        if loss_printed and "budget" in summary(err)["conditions"]:
            outcomes.add(code)
    assert outcomes == {EXIT_LOSS}


# Which zips are expected


def with_zips(batches: list[int], **kwargs) -> FakeServer:
    listings = FIXTURES["listings"] | {f"covers_0014_{b:02d}": full("0014", b) for b in batches if b not in (61, 62)}
    return FakeServer(listings, zips={"covers_0014": [f"covers_0014_{b:02d}" for b in batches]}, **kwargs)


def test_backlog_above_the_newest_zip_is_never_missing():
    code, rows, _ = run_to_strings(known=KNOWN)
    assert code == EXIT_OK
    assert missing_zips(rows) == []


def test_a_zip_gone_from_below_the_newest_is_inferred_missing_and_indeterminate():
    code, rows, _ = run_to_strings(with_zips([58, 59, 61, 62]), known=KNOWN, main_batches=5)
    assert missing_zips(rows) == [("covers_0014_60", "below_newest")]
    assert code == EXIT_INDETERMINATE


def test_a_zip_named_in_the_baseline_that_is_gone_is_a_loss():
    code, rows, _ = run_to_strings(with_zips([61, 62]), known=KNOWN, baseline={"covers_0014_63"})
    assert missing_zips(rows) == [("covers_0014_63", "baseline")]
    assert code == EXIT_LOSS


def test_without_a_baseline_a_deleted_newest_zip_nothing_was_finalized_into_is_not_seen():
    code, rows, _ = run_to_strings(with_zips([61, 62]), known=KNOWN)
    assert code == EXIT_OK
    assert missing_zips(rows) == []


def test_a_known_loss_gone_from_its_item_is_a_loss():
    code, rows, _ = run_to_strings(with_zips([60, 61]), known=KNOWN)
    assert missing_zips(rows) == [("covers_0014_62", "known")]
    assert code == EXIT_LOSS


def test_a_zip_a_cover_points_into_that_is_gone_is_a_loss():
    server = with_zips([61, 62, 63])
    server.listings["covers_0014_63"] = [14630000, 14639998]
    server.pointers[14639999] = {"id": 14639999, "filename": "covers_0014/covers_0014_59.zip"}
    code, rows, _ = run_to_strings(server, known=KNOWN, main_batches=3)
    assert missing_zips(rows) == [("covers_0014_59", "pointer")]
    assert code == EXIT_LOSS


def test_pointer_evidence_upgrades_an_inferred_missing_zip():
    server = with_zips([58, 60, 61, 62, 63])
    server.listings["covers_0014_63"] = [14630000, 14639998]
    server.pointers[14639999] = {"id": 14639999, "filename": "covers_0014/covers_0014_59.zip"}
    code, rows, _ = run_to_strings(server, known=KNOWN, main_batches=6)
    assert missing_zips(rows) == [("covers_0014_59", "pointer")]
    assert code == EXIT_LOSS


def test_a_missing_zip_that_reappears_on_the_second_read_is_indeterminate():
    again = [f"covers_0014_{b}" for b in (58, 59, 60, 61, 62)]
    code, rows, _ = run_to_strings(with_zips([58, 59, 61, 62], second_metadata={"covers_0014": again}), known=KNOWN, main_batches=5)
    assert [r.get("error") for r in rows if r["batch"] == "covers_0014_60"] == ["absence not confirmed by a second read of the item"]
    assert code == EXIT_INDETERMINATE


def test_a_failed_second_read_never_confirms_a_missing_zip():
    server = with_zips([61, 62], second_metadata={"covers_0014": None})
    code, rows, _ = run_to_strings(server, known=KNOWN, baseline={"covers_0014_63"})
    assert [(r["verdict"], r.get("error")) for r in rows if r["batch"] == "covers_0014_63"] == [
        ("indeterminate", "absence not confirmed by a second read of the item")
    ]
    assert code == EXIT_INDETERMINATE


def test_an_item_inside_the_window_without_metadata_gets_a_row_not_silence():
    batches = list(range(63))
    server = with_zips(batches)  # covers_0013 is not served: archive.org answers {}
    code, rows, _ = run_to_strings(server, known=KNOWN, main_batches=70)
    assert [r for r in rows if r["batch"] == "covers_0013"] == [
        {"batch": "covers_0013", "listing_count": 0, "verdict": "indeterminate", "evidence_ids": [], "error": "item lists no zips"}
    ]
    assert code == EXIT_INDETERMINATE


def test_the_main_scope_straddles_an_item_boundary():
    listings = FIXTURES["listings"] | {f"covers_0014_{b}": full("0014", b) for b in range(63, 100)} | {"covers_0015_00": full("0015", 0)}
    zips = {"covers_0014": [f"covers_0014_{b}" for b in range(61, 100)], "covers_0015": ["covers_0015_00"]}
    code, rows, _ = run_to_strings(FakeServer(listings, zips=zips), known=KNOWN, main_batches=40)
    batches = [r["batch"] for r in rows]
    assert code == EXIT_OK
    assert len(batches) == 40
    assert {"covers_0014_61", "covers_0014_99", "covers_0015_00"} <= set(batches)


def test_the_census_path_needs_its_own_request_cap():
    with pytest.raises(SystemExit) as e:
        main(["--items", "0012"])
    assert e.value.code == 2


def test_a_deleted_newest_zip_that_covers_point_into_is_caught_without_the_gallop():
    class NoGallop(Checker):
        def newest_cover_id(self, floor):
            return NEWEST_COVER

    server = with_zips([61, 62])  # covers_0014_63 was finalized, then deleted
    server.pointers |= {14630000: {"id": 14630000, "filename": "covers_0014/covers_0014_63.zip"}}
    code, rows, _ = run_to_strings(server, known=KNOWN, checker_cls=NoGallop)
    assert missing_zips(rows) == [("covers_0014_63", "pointer")]
    assert code == EXIT_LOSS
