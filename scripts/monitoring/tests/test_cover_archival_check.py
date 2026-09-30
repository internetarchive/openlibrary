import io
import json
from datetime import date
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
    SERVES_PRESENT_ID,
    Checker,
    Http,
    Zip,
    classify_pointer,
    load_known_losses,
    rotation_slots,
    run,
    sample_missing,
)

FIXTURES = json.loads((Path(__file__).parent / "cover_archival_fixtures.json").read_text())
HEADER_LINE, ROW = FIXTURES["listing_page_lines"]
KNOWN = load_known_losses()


def listing_page(zip_name: str, first: int, last: int) -> str:
    """Rebuild a listing page from its recorded ID range and the verbatim row format."""
    rows = [ROW.replace("covers_0014_62.zip", f"{zip_name}.zip").replace("0014620000", f"{i:010d}") for i in range(first, last + 1)]
    return "\n".join([HEADER_LINE, *rows])


def make_http(listings=None, pointers=None, zips=None, heads=None, max_requests=1000) -> Http:
    listings = FIXTURES["listings"] if listings is None else listings
    pointers = {p["id"]: p for p in FIXTURES["pointers"]} if pointers is None else pointers
    zips = zips or {"covers_0014": sorted(listings)}
    heads = {h["id"]: h["status"] for h in FIXTURES["heads"]} | (heads or {})

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://archive.org/metadata/"):
            item = url.rsplit("/", 1)[1]
            if item not in zips:
                return httpx.Response(200, json=FIXTURES["missing_item_metadata"])
            if zips[item] is None:
                return httpx.Response(500)
            return httpx.Response(200, json={"files": [{"name": f"{n}.zip"} for n in zips[item]]})
        if url.startswith("https://archive.org/download/"):
            name = url.rstrip("/").rsplit("/", 1)[1].removesuffix(".zip")
            if name not in listings:
                return httpx.Response(404)
            return httpx.Response(200, text=listing_page(name, *listings[name]))
        if request.method == "HEAD":
            cover_id = int(request.url.path.rsplit("/", 1)[1].split("-")[0])
            status = heads.get(cover_id, 200)
            if status == 404 and request.url.params.get("default") != "false":
                return httpx.Response(200, headers={"Content-Type": "image/gif"})  # the placeholder
            return httpx.Response(status)
        cover_id = int(url.rsplit("/", 1)[1].removesuffix(".json"))
        if cover_id not in pointers:
            return httpx.Response(404)
        return httpx.Response(200, json=pointers[cover_id])

    return Http(max_requests=max_requests, delay=0, client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_fixtures_hold_only_id_and_filename():
    assert all(set(p) == {"id", "filename"} for p in FIXTURES["pointers"])


def test_known_losses_file_names_batch_62_with_its_evidence():
    assert KNOWN["covers_0014_62"]["missing_count"] == 5927
    assert POSITIVE_CONTROL_ID in KNOWN["covers_0014_62"]["evidence_ids"]


def test_positive_control_batch_62_reads_as_loss():
    checker = Checker(make_http())
    assert checker.id_verdict(POSITIVE_CONTROL_ID) == "LOSS"
    row = checker.check(Zip("", "0014", 62))
    assert row == {
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
    assert row["listing_count"] == 10_000
    assert row["verdict"] == "ok"


def test_each_listed_cover_counts_once_though_its_row_names_it_twice():
    checker = Checker(make_http())
    assert checker.listing(Zip("", "0014", 62)) == set(range(14620000, 14624073))


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
    ],
)
def test_classify_pointer(status, filename, listed, expected):
    assert classify_pointer(14627720, status, filename, Zip("", "0014", 62), listed) == expected


def test_sample_missing_takes_all_of_a_small_gap_and_five_of_a_large_one():
    assert sample_missing([1, 2, 3, 4, 5, 6]) == [1, 2, 3, 4, 5, 6]
    assert sample_missing(list(range(100, 201))) == [100, 125, 150, 175, 200]


def small_batch(filename: str | None):
    """Batch 26 of a fake item, missing one ID whose record says ``filename``."""
    listings = {"covers_0014_26": [14260000, 14269998]}
    pointers = {} if filename is None else {14269999: {"id": 14269999, "filename": filename}}
    return listings, pointers


def test_partial_row_records_whether_the_local_copy_still_serves():
    listings, pointers = small_batch("2023/04/21/OL47642877M-X0Chl.jpg")
    row = Checker(make_http(listings, pointers)).check(Zip("", "0014", 26))
    assert (row["verdict"], row["serves"], row["evidence_ids"]) == ("partial", 200, [14269999])


def test_partial_that_actually_redirects_is_loss():
    listings, pointers = small_batch("2023/04/21/OL47642877M-X0Chl.jpg")
    row = Checker(make_http(listings, pointers, heads={14269999: 302})).check(Zip("", "0014", 26))
    assert (row["verdict"], row["serves"]) == ("LOSS", 302)


def test_missing_ids_without_records_are_not_loss():
    listings, pointers = small_batch(None)
    row = Checker(make_http(listings, pointers)).check(Zip("", "0014", 26))
    assert row["verdict"] == "short_no_record"
    assert "serves" not in row


def test_an_empty_listing_is_indeterminate_not_a_short_batch():
    checker = Checker(make_http(listings={"covers_0014_61": [1, 0]}))
    assert checker.check(Zip("", "0014", 61))["verdict"] == "indeterminate"


def run_to_strings(http: Http, known=None, items=("0014",)):
    out, err = io.StringIO(), io.StringIO()
    code = run(Checker(http), list(items), [""], {} if known is None else known, rotate_zips=0, out=out, err=err)
    return code, [json.loads(r) for r in out.getvalue().splitlines()], err.getvalue().splitlines()


def test_run_reports_loss_with_both_controls_passing():
    code, rows, err = run_to_strings(make_http())
    assert code == EXIT_LOSS
    assert [(r["batch"], r["verdict"]) for r in rows] == [
        ("covers_0014_61", "ok"),
        ("covers_0014_62", "LOSS"),
    ]
    summary = json.loads(err[-1])
    assert "batch" not in summary
    assert summary["summary"] == {"ok": 1, "LOSS": 1}
    assert summary["positive_control"] == "live"


def test_a_known_loss_is_reported_but_does_not_alert():
    code, rows, err = run_to_strings(make_http(), known=KNOWN)
    assert code == EXIT_OK
    assert rows[1] | {"known": True} == rows[1]
    assert json.loads(err[-1])["known_losses"] == {"covers_0014_62": "unchanged"}


def test_a_known_loss_is_checked_even_outside_the_scope():
    listings = FIXTURES["listings"] | {"covers_0013_00": [13000000, 13009999]}
    zips = {"covers_0013": ["covers_0013_00"]}
    code, rows, _ = run_to_strings(make_http(listings, zips=zips), known=KNOWN, items=("0013",))
    assert code == EXIT_OK
    assert [r["batch"] for r in rows] == ["covers_0013_00", "covers_0014_62"]


@pytest.mark.parametrize("zips", [{}, {"covers_0014": []}], ids=["missing-item", "no-zips"])
def test_an_item_without_zips_is_indeterminate_not_zero_covers(zips):
    code, rows, _ = run_to_strings(make_http(zips=zips or {"elsewhere": []}))
    assert code == EXIT_INDETERMINATE
    assert rows == [{"batch": "covers_0014", "listing_count": 0, "verdict": "indeterminate", "evidence_ids": [], "error": "item lists no zips"}]


def test_an_unreadable_known_loss_listing_is_a_control_failure_not_a_repair():
    listings = {"covers_0014_61": FIXTURES["listings"]["covers_0014_61"]}
    code, rows, err = run_to_strings(make_http(listings, zips={"covers_0014": ["covers_0014_61"]}), known=KNOWN)
    assert code == EXIT_CONTROL
    assert rows == []
    assert any("known loss covers_0014_62" in line for line in err)


def test_the_positive_control_fails_on_an_unreadable_listing():
    checker = Checker(make_http({"covers_0014_61": FIXTURES["listings"]["covers_0014_61"]}))
    assert checker.id_verdict(POSITIVE_CONTROL_ID) == "indeterminate"


def with_expected_missing(n: int) -> dict:
    return {"covers_0014_62": KNOWN["covers_0014_62"] | {"missing_count": n}}


def test_a_known_loss_that_grew_is_a_new_loss():
    code, rows, err = run_to_strings(make_http(), known=with_expected_missing(5000))
    assert code == EXIT_LOSS
    assert rows[1]["known"] is False
    assert json.loads(err[-1])["known_losses"] == {"covers_0014_62": "grew"}


def test_a_known_loss_that_shrank_marks_the_list_stale():
    code, _, err = run_to_strings(make_http(), known=with_expected_missing(6000))
    assert code == EXIT_STALE
    assert json.loads(err[-1])["known_losses"] == {"covers_0014_62": "shrank"}


def test_a_repaired_positive_case_leaves_the_control_on_the_fixture_only():
    listings = dict(FIXTURES["listings"]) | {"covers_0014_62": [14620000, 14629999]}
    code, rows, err = run_to_strings(make_http(listings), known=KNOWN)
    assert code == EXIT_STALE
    assert rows[1]["verdict"] == "ok"
    summary = json.loads(err[-1])
    assert summary["positive_control"] == "fixture_only"
    assert summary["known_losses"] == {"covers_0014_62": "shrank"}


def test_a_known_loss_that_reads_as_something_else_fails_the_controls():
    pointers = {p["id"]: p for p in FIXTURES["pointers"]}
    for i in (14624073, 14628517, 14629999):
        pointers[i] = {"id": i, "filename": "covers_0014/covers_0014_61.zip"}
    code, rows, err = run_to_strings(make_http(pointers=pointers), known=KNOWN)
    assert code == EXIT_CONTROL
    assert rows == []
    assert any("known loss covers_0014_62" in line for line in err)


@pytest.mark.parametrize(("cover_id", "status"), [(SERVES_PRESENT_ID, 404), (SERVES_ABSENT_ID, 200)])
def test_a_failed_serves_control_suppresses_every_verdict(cover_id, status):
    code, rows, err = run_to_strings(make_http(heads={cover_id: status}))
    assert code == EXIT_CONTROL
    assert rows == []
    assert any("serves control" in line for line in err)


def test_serves_asks_for_no_placeholder():
    checker = Checker(make_http())
    assert checker.serves(SERVES_ABSENT_ID) == 404
    assert checker.serves(SERVES_PRESENT_ID) == 200


def test_an_unreadable_listing_is_indeterminate_not_a_crash():
    zips = {"covers_0014": ["covers_0014_61", "covers_0014_62", "covers_0014_63"]}
    code, rows, _ = run_to_strings(make_http(zips=zips), known=KNOWN)
    assert code == EXIT_INDETERMINATE
    assert rows[2] == {"batch": "covers_0014_63", "listing_count": 0, "verdict": "indeterminate", "evidence_ids": []}


def test_run_is_clean_when_nothing_is_short():
    listings = dict(FIXTURES["listings"])
    zips = {"covers_0014": ["covers_0014_61"]}
    code, rows, _ = run_to_strings(make_http(listings, zips=zips))
    assert code == EXIT_OK
    assert len(rows) == 1


@pytest.mark.parametrize(
    "broken",
    [
        # The positive control's record no longer points at batch 62.
        lambda listings, pointers: pointers.__setitem__(POSITIVE_CONTROL_ID, {"id": POSITIVE_CONTROL_ID, "filename": "2024/05/16/OL1M-x.jpg"}),
        # Batch 61's listing lost the negative control.
        lambda listings, pointers: listings.__setitem__("covers_0014_61", [14610000, 14614999]),
    ],
    ids=["positive", "negative"],
)
def test_a_failed_control_suppresses_every_verdict(broken):
    listings = dict(FIXTURES["listings"])
    pointers = {p["id"]: p for p in FIXTURES["pointers"]}
    broken(listings, pointers)
    code, rows, err = run_to_strings(make_http(listings, pointers))
    assert code == EXIT_CONTROL
    assert rows == []
    assert any("control_failed" in line for line in err)


def test_indeterminate_exits_non_zero():
    pointers = {p["id"]: p for p in FIXTURES["pointers"]}
    for i in (14624073, 14625555, 14627036, 14628517, 14629999):
        pointers[i] = {"id": i, "filename": "covers_0014/covers_0014_61.zip"}
    code, _, _ = run_to_strings(make_http(pointers=pointers))
    assert code == EXIT_INDETERMINATE


def test_hitting_the_request_cap_fails_loudly():
    code, _, err = run_to_strings(make_http(max_requests=5))
    assert code == EXIT_BUDGET
    assert "budget_exceeded" in err[0]


def test_rotation_skips_the_default_pass_and_visits_every_other_window():
    slots = rotation_slots(["0014"], 30)
    assert ("", "0014", 0) not in slots
    assert ("l", "0014", 60) in slots
    assert ("", "0008", 90) in slots
    assert len(slots) == len(set(slots)) == (6 * 4 + 3) * 4


def test_rotation_adds_one_window_chosen_by_week():
    zips = {"covers_0014": ["covers_0014_61"], "l_covers_0008": [f"l_covers_0008_{b:02d}" for b in range(100)]}
    listings = {"covers_0014_61": FIXTURES["listings"]["covers_0014_61"], "covers_0014_62": [14620000, 14624072]}
    listings |= {f"l_covers_0008_{b:02d}": [8_000_000 + b * 10_000, 8_000_000 + b * 10_000 + 9_999] for b in range(100)}
    slots = rotation_slots(["0014"], 30)
    week = slots.index(("l", "0008", 30))
    today = date.fromordinal(week * 7 + 7 * len(slots) * 1000)
    out, err = io.StringIO(), io.StringIO()
    run(Checker(make_http(listings, zips=zips)), ["0014"], [""], {}, rotate_zips=30, today=today, out=out, err=err)
    batches = [json.loads(r)["batch"] for r in out.getvalue().splitlines()]
    assert batches == ["covers_0014_61"] + [f"l_covers_0008_{b:02d}" for b in range(30, 60)]


def test_an_unexpected_error_is_indeterminate_never_the_loss_exit():
    code, rows, err = run_to_strings(make_http(zips={"covers_0014": None}))
    assert code == EXIT_INDETERMINATE
    assert rows == []
    assert json.loads(err[-1]) == {"error": "HTTPStatusError"}


@pytest.mark.parametrize("broken_id", [POSITIVE_CONTROL_ID, NEGATIVE_CONTROL_ID], ids=["positive", "negative"])
def test_the_controls_run_whatever_the_scope(broken_id):
    pointers = {p["id"]: p for p in FIXTURES["pointers"]}
    pointers[broken_id] = {"id": broken_id, "filename": "2024/05/16/OL1M-x.jpg"}
    listings = FIXTURES["listings"] | {"covers_0013_00": [13000000, 13009999]}
    zips = {"covers_0013": ["covers_0013_00"]}
    code, rows, _ = run_to_strings(make_http(listings, pointers, zips=zips), items=("0013",))
    assert code == EXIT_CONTROL
    assert rows == []
