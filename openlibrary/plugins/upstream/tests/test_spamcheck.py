"""Tests for the log-only form signals in spamcheck (honeypot + time-to-submit)."""

import datetime as dt
import json
import logging
import re
from pathlib import Path
from unittest.mock import Mock

import pytest
import web

from openlibrary.utils.request_context import site

from .. import spamcheck

TEMPLATES = Path(__file__).parents[3] / "templates"


@pytest.fixture
def signals(monkeypatch, caplog):
    """Sign in as a ten-day-old account and collect what gets recorded: `.logged()` records and `.counted` stats keys."""
    user = Mock(key="/people/alice", created=dt.datetime.now() - dt.timedelta(days=10, hours=1))
    token = site.set(Mock(get_user=lambda: user))
    monkeypatch.setattr(spamcheck, "get_secret_key", lambda: "test-secret")
    counted: list[str] = []
    monkeypatch.setattr(spamcheck.stats, "increment", lambda key, *a, **kw: counted.append(key))
    caplog.set_level(logging.INFO, logger="openlibrary.spam_signals")

    def logged():
        return [json.loads(r.getMessage().split(" ", 1)[1]) for r in caplog.records if r.getMessage().startswith("form_signals ")]

    yield web.storage(user=user, counted=counted, logged=logged)
    site.reset(token)


def token_aged(monkeypatch, seconds: float, surface: str = "add-book") -> str:
    """A genuine token that was rendered `seconds` ago."""
    now = spamcheck.time.time()
    monkeypatch.setattr(spamcheck.time, "time", lambda: now - seconds)
    token = spamcheck.make_form_token(surface)
    monkeypatch.setattr(spamcheck.time, "time", lambda: now)
    return token


class TestRecordFormSignals:
    def test_normal_submission(self, signals, monkeypatch):
        form = web.storage(book_title="Book", ol_extra_notes="", ol_form_token=token_aged(monkeypatch, 42))
        spamcheck.record_form_signals("add-book", form)

        assert signals.logged() == [
            {"surface": "add-book", "username": "alice", "account_age_days": 10, "honeypot_filled": False, "timing": "ok", "elapsed_seconds": 42.0}
        ]
        assert signals.counted == ["ol.spam_signals.add-book.timing.ok"]

    def test_takes_its_fields_out_of_the_form(self, signals, monkeypatch):
        form = web.storage(book_title="Book", ol_extra_notes="x", ol_form_token=token_aged(monkeypatch, 42))
        spamcheck.record_form_signals("add-book", form)
        assert form == {"book_title": "Book"}

    def test_honeypot_filled(self, signals, monkeypatch):
        form = web.storage(ol_extra_notes="  buy cheap pills " + "x" * 500, ol_form_token=token_aged(monkeypatch, 42))
        spamcheck.record_form_signals("add-book", form)

        (record,) = signals.logged()
        assert record["honeypot_filled"] is True
        assert record["honeypot_sample"] == ("buy cheap pills " + "x" * 500)[: spamcheck.HONEYPOT_SAMPLE_CHARS]
        assert "x" * (spamcheck.HONEYPOT_SAMPLE_CHARS + 1) not in json.dumps(record)
        assert signals.counted == ["ol.spam_signals.add-book.honeypot_filled", "ol.spam_signals.add-book.timing.ok"]

    def test_whitespace_in_the_honeypot_is_not_a_fill(self, signals, monkeypatch):
        spamcheck.record_form_signals("add-book", web.storage(ol_extra_notes="  ", ol_form_token=token_aged(monkeypatch, 42)))
        assert signals.logged()[0]["honeypot_filled"] is False

    @pytest.mark.parametrize(
        ("seconds", "timing"),
        [
            (spamcheck.FAST_SUBMIT_SECONDS - 1, "fast"),
            (spamcheck.FAST_SUBMIT_SECONDS + 1, "ok"),
            (spamcheck.STALE_TOKEN_SECONDS + 60, "stale"),
        ],
    )
    def test_thresholds_only_label_the_submission(self, signals, monkeypatch, seconds, timing):
        spamcheck.record_form_signals("add-book", web.storage(ol_form_token=token_aged(monkeypatch, seconds)))

        (record,) = signals.logged()
        assert record["timing"] == timing
        assert record["elapsed_seconds"] == pytest.approx(seconds, abs=0.2)
        assert signals.counted == [f"ol.spam_signals.add-book.timing.{timing}"]

    @pytest.mark.parametrize("form", [{}, {"ol_form_token": ""}])
    def test_missing_token(self, signals, form):
        spamcheck.record_form_signals("add-book", web.storage(form))

        (record,) = signals.logged()
        assert (record["timing"], record["elapsed_seconds"]) == ("missing", None)
        assert signals.counted == ["ol.spam_signals.add-book.timing.missing"]

    @pytest.mark.parametrize(
        "forge",
        [
            pytest.param(lambda t: t[:-1] + ("0" if t[-1] != "0" else "1"), id="altered-signature"),
            pytest.param(lambda t: "|".join([t.split("|")[0], "1.000", t.split("|")[2]]), id="altered-rendered-at"),
            pytest.param(lambda t: t.replace("add-book", "add-book-check", 1), id="relabelled"),
            pytest.param(lambda t: "add-book|not-a-number|é", id="non-ascii"),
            pytest.param(lambda t: "garbage", id="garbage"),
            pytest.param(lambda t: t + "|extra", id="extra-part"),
        ],
    )
    def test_forged_token(self, signals, monkeypatch, forge):
        spamcheck.record_form_signals("add-book", web.storage(ol_form_token=forge(token_aged(monkeypatch, 42))))

        (record,) = signals.logged()
        assert (record["timing"], record["elapsed_seconds"]) == ("invalid", None)
        assert signals.counted == ["ol.spam_signals.add-book.timing.invalid"]

    def test_token_from_another_account_is_invalid(self, signals, monkeypatch):
        token = token_aged(monkeypatch, 42)
        signals.user.key = "/people/mallory"
        spamcheck.record_form_signals("add-book", web.storage(ol_form_token=token))
        assert signals.logged()[0]["timing"] == "invalid"

    def test_token_from_another_form_is_invalid(self, signals, monkeypatch):
        spamcheck.record_form_signals("add-book", web.storage(ol_form_token=token_aged(monkeypatch, 42, surface="list")))
        assert signals.logged()[0]["timing"] == "invalid"

    def test_a_later_page_of_the_same_flow_is_logged_under_its_own_name(self, signals, monkeypatch):
        spamcheck.record_form_signals("add-book", web.storage(ol_form_token=token_aged(monkeypatch, 42, surface="add-book-check")))

        assert signals.logged()[0]["surface"] == "add-book-check"
        assert signals.counted == ["ol.spam_signals.add-book-check.timing.ok"]

    def test_logged_out(self, signals, monkeypatch):
        site.get().get_user = lambda: None
        spamcheck.record_form_signals("add-book", web.storage(ol_form_token=token_aged(monkeypatch, 42)))

        (record,) = signals.logged()
        assert (record["username"], record["account_age_days"], record["timing"]) == (None, None, "ok")

    def test_reads_web_input_when_no_form_is_given(self, signals, monkeypatch):
        token = token_aged(monkeypatch, 42, surface="list")
        monkeypatch.setattr(web, "input", lambda: web.storage(ol_extra_notes="spam", ol_form_token=token))
        spamcheck.record_form_signals("list")

        (record,) = signals.logged()
        assert (record["surface"], record["honeypot_filled"], record["timing"]) == ("list", True, "ok")

    def test_formless_submission_is_counted_without_form_signals(self, signals):
        spamcheck.record_formless_submission("list-json")

        assert signals.logged() == [
            {"surface": "list-json", "username": "alice", "account_age_days": 10, "honeypot_filled": False, "timing": "no-form", "elapsed_seconds": None}
        ]
        assert signals.counted == ["ol.spam_signals.list-json.timing.no-form"]


class TestNeverRaises:
    @pytest.fixture(params=["get_user", "stats", "secret", "logging"])
    def broken(self, signals, monkeypatch, request):
        token = token_aged(monkeypatch, 42)
        boom = Mock(side_effect=RuntimeError("boom"))
        if request.param == "get_user":
            site.get().get_user = boom
        elif request.param == "stats":
            monkeypatch.setattr(spamcheck.stats, "increment", boom)
        elif request.param == "secret":
            monkeypatch.setattr(spamcheck, "get_secret_key", boom)
        else:
            monkeypatch.setattr(spamcheck.signals_logger, "info", boom)
        return token

    def test_record_form_signals(self, broken):
        form = web.storage(book_title="Book", ol_extra_notes="x", ol_form_token=broken)
        assert spamcheck.record_form_signals("add-book", form) is None
        assert form == {"book_title": "Book"}

    def test_record_formless_submission(self, broken):
        assert spamcheck.record_formless_submission("list-json") is None

    def test_make_form_token_is_blank_when_it_cannot_be_signed(self, signals, monkeypatch):
        monkeypatch.setattr(spamcheck, "get_secret_key", Mock(side_effect=KeyError("secret_key")))
        assert spamcheck.make_form_token("add-book") == ""

    @pytest.mark.parametrize("form", [None, "not a mapping", {"ol_extra_notes": ["a", "list"], "ol_form_token": 7}])
    def test_unexpected_input(self, signals, monkeypatch, form):
        monkeypatch.setattr(web, "input", Mock(side_effect=RuntimeError("no request")))
        assert spamcheck.record_form_signals("add-book", form) is None


class TestFormSignalsTemplate:
    """The partial hardcodes the field names; keep it in step with the constants and with what makes a honeypot safe."""

    html = (TEMPLATES / "lib" / "form_signals.html").read_text()

    def test_field_names_match_the_constants(self):
        assert f'name="{spamcheck.FORM_TOKEN_FIELD}" value="$make_form_token(surface)"' in self.html
        assert f'name="{spamcheck.HONEYPOT_FIELD}"' in self.html

    def test_honeypot_is_hidden_from_people_without_display_none(self):
        assert '<div class="shift" aria-hidden="true">' in self.html
        honeypot = self.html.split('<div class="shift" aria-hidden="true">')[1]
        assert "hidden" not in honeypot
        for attr in ('type="text"', 'tabindex="-1"', 'autocomplete="off"', 'value=""'):
            assert attr in honeypot

    def test_renders_a_token_the_post_accepts(self, render_template, signals, monkeypatch):
        html = render_template("lib/form_signals", "add-book")
        token = re.search(r'name="ol_form_token" value="([^"]+)"', html).group(1)
        now = spamcheck.time.time()
        monkeypatch.setattr(spamcheck.time, "time", lambda: now + 30)
        spamcheck.record_form_signals("add-book", web.storage(ol_form_token=token))

        assert 'name="ol_extra_notes" value=""' in html
        assert (signals.logged()[0]["timing"], signals.logged()[0]["elapsed_seconds"]) == ("ok", 30.0)

    @pytest.mark.parametrize(
        ("template", "surface"),
        [("books/add.html", '"add-book"'), ("books/check.html", '"add-book-check"'), ("type/list/edit.html", "list_type")],
    )
    def test_creation_forms_include_it(self, template, surface):
        assert f'$:render_template("lib/form_signals", {surface})' in (TEMPLATES / template).read_text()
