"""Tests for Core Vitals retention scoring (issue #11956).

Two bugs found in the prototype are pinned by regression tests here:

1. ``dimension1`` is a flat field on the visit, not nested under
   ``customDimensions``. Reading it wrongly silently classified every visit as
   ``visitor`` and undercounted the score ~5.85x.
2. ``follow`` / ``readlog_*`` events have been tracked app-side since PR #12367
   but were absent from the scoring table, so they counted for nothing.
"""

import datetime
import json as jsonlib
import pathlib
import subprocess
import sys
from typing import ClassVar
from unittest.mock import Mock

import pytest

from openlibrary.core import matomo, retention
from openlibrary.core.matomo import VisitFetch


def _visit(dimension1="visitor", visitor_id="v1", user_id=None, events=(), urls=(), timestamp=None):
    """Build a Live.getLastVisitsDetails-shaped visit record."""
    actions = [{"type": "event", "eventCategory": category, "eventAction": action} for category, action in events]
    actions += [{"type": "action", "url": url} for url in urls]
    visit = {
        "dimension1": dimension1,
        "visitorId": visitor_id,
        "userId": user_id,
        "actionDetails": actions,
    }
    if timestamp is not None:
        visit["firstActionTimestamp"] = timestamp
    return visit


def _stub_client(visits, truncated_reason=None):
    """A stand-in MatomoClient returning a real VisitFetch.

    Using the real dataclass rather than a Mock means the truncation signal
    cannot be accidentally truthy -- an auto-created Mock attribute is, which
    previously made every stubbed fetch look truncated.
    """
    client = Mock()
    client.get_visits_since.return_value = VisitFetch(list(visits), truncated_reason=truncated_reason)
    return client


def _gather(visits, hours=1):
    return retention.gather_retention_scores(client=_stub_client(visits), hours=hours)


class TestEventPointsMatchTheSchema:
    """Pin the weights to the Score Schemas spreadsheet (gid=41518278).

    Transcribed from the source of truth. If the spreadsheet changes, this test
    should be updated in the same commit as EVENT_POINTS -- the point is that
    the two can never drift apart unnoticed.
    """

    SCHEMA: ClassVar[dict[str, int]] = {
        "import_goodreads": 200,
        "set_reading_goal": 150,
        "read": 100,
        "search_inside": 75,
        "list_create": 50,
        "follow": 50,
        "edit": 25,
        "readlog_completion": 20,
        "star_rating": 20,
        "readlog_currently_reading": 15,
        "readlog_want_to_read": 10,
        "checkin": 10,
        "explorer_view": 10,
        "search": 5,
        "book_view": 5,
        "author_view": 5,
        "mybooks_view": 5,
    }

    def test_points_match_exactly(self):
        assert retention.EVENT_POINTS == self.SCHEMA

    def test_every_mapped_event_has_a_point_value(self):
        mapped = set(retention.RETENTION_EVENTS.values()) | set(retention.PAGE_EVENTS.values())
        assert mapped <= set(retention.EVENT_POINTS)

    def test_every_schema_event_is_either_mapped_or_declared_untracked(self):
        """A schema event that is neither scored nor listed as a gap is invisible."""
        mapped = set(retention.RETENTION_EVENTS.values()) | set(retention.PAGE_EVENTS.values())
        assert mapped | set(retention.UNTRACKED_EVENTS) == set(retention.EVENT_POINTS)

    def test_untracked_events_carry_their_schema_points(self):
        for name, points in retention.UNTRACKED_EVENTS.items():
            assert points == self.SCHEMA[name]


class TestReadMapping:
    """`read` is the highest-weight event; it silently scored 0 for the whole
    prototype because it was mapped to a Matomo category that does not exist."""

    @pytest.mark.parametrize("action", ["Read", "Borrow", "PrintDisabled", "ReadListen", "BorrowListen", "Listen"])
    def test_every_route_to_the_content_counts_as_a_read(self, action):
        assert retention._score_visit(_visit(events=[("CTAClick", action)])) == {"read": 100}

    def test_borrow_is_worth_the_same_as_read(self):
        """Borrowing is reading behind a lending gate, not a weaker signal."""
        borrow = retention._score_visit(_visit(events=[("CTAClick", "Borrow")]))
        read = retention._score_visit(_visit(events=[("CTAClick", "Read")]))
        assert borrow == read

    def test_the_dead_embed_mapping_is_gone(self):
        """`Embed` is not a category Matomo ever emits for openlibrary.org."""
        assert not any(category == "Embed" for category, _ in retention.RETENTION_EVENTS)

    @pytest.mark.parametrize("action", ["JoinWaitlist", "LeaveWaitlist", "Locate", "CheckedOut", "Preview"])
    def test_actions_that_do_not_deliver_content_are_not_reads(self, action):
        assert retention._score_visit(_visit(events=[("CTAClick", action)])) == {}


class TestCohortToClass:
    @pytest.mark.parametrize(
        ("cohort", "expected"),
        [
            ("visitor", "visitor"),
            ("d0", "registrant"),
            ("d1+", "returning"),
            ("d7+", "returning"),
            ("d14+", "returning"),
            ("d30+", "returning"),
            ("d90+", "retained"),
        ],
    )
    def test_every_cohort_maps_to_a_class(self, cohort, expected):
        assert retention._cohort_to_class(cohort) == expected

    def test_all_cohorts_are_covered_exactly_once(self):
        """No cohort may be double-counted or dropped -- that would silently skew the score."""
        assigned = [cohort for info in retention.PATRON_CLASSES.values() for cohort in info["cohorts"]]
        assert sorted(assigned) == sorted(retention.COHORTS)
        assert len(assigned) == len(set(assigned))

    def test_unknown_cohort_falls_back_to_visitor(self):
        assert retention._cohort_to_class("nonsense") == "visitor"

    def test_class_weights_match_the_spec(self):
        weights = {cls: info["weight"] for cls, info in retention.PATRON_CLASSES.items()}
        assert weights == {"visitor": 0.01, "registrant": 0.20, "returning": 0.50, "retained": 1.00}


class TestScoreVisit:
    def test_scores_a_known_custom_event(self):
        assert retention._score_visit(_visit(events=[("CTAClick", "Read")])) == {"read": 100}

    def test_ignores_unknown_events(self):
        assert retention._score_visit(_visit(events=[("Nope", "Nothing")])) == {}

    def test_caps_each_event_type_at_once_per_visit(self):
        """Ten rapid clicks are one expression of intent, not ten."""
        visit = _visit(events=[("CTAClick", "Read")] * 10)
        assert retention._score_visit(visit) == {"read": 100}

    def test_different_event_types_accumulate(self):
        visit = _visit(events=[("CTAClick", "Read"), ("MainNav", "Explore")])
        assert retention._score_visit(visit) == {"read": 100, "explorer_view": 10}

    def test_scores_page_view_events_by_url_path_prefix(self):
        visit = _visit(urls=["https://openlibrary.org/works/OL45W/Book", "https://openlibrary.org/search?q=x"])
        assert retention._score_visit(visit) == {"book_view": 5, "search": 5}

    def test_tolerates_a_missing_action_details(self):
        assert retention._score_visit({"dimension1": "d0"}) == {}

    def test_tolerates_a_null_action_details(self):
        assert retention._score_visit({"actionDetails": None}) == {}

    @pytest.mark.parametrize(
        ("category", "action", "event_name"),
        [
            ("FollowsPage", "Follow", "follow"),
            ("MyBooksPageHeader", "Follow", "follow"),
            ("ListCardCarousel", "Follow", "follow"),
            ("PatronPage", "Follow", "follow"),
            ("ReadingLog", "WantToRead", "readlog_want_to_read"),
            ("ReadingLog", "CurrentlyReading", "readlog_currently_reading"),
            ("ReadingLog", "AlreadyRead", "readlog_completion"),
        ],
    )
    def test_regression_follow_and_readlog_events_are_scored(self, category, action, event_name):
        """These are tracked app-side by PR #12367; scoring them as 0 was bug 2."""
        scored = retention._score_visit(_visit(events=[(category, action)]))
        assert event_name in scored
        assert scored[event_name] > 0


class TestGatherRetentionScores:
    def test_regression_reads_dimension1_as_a_flat_field(self):
        """Bug 1: reading a nested `customDimensions` made every visit a `visitor`."""
        result = _gather([_visit(dimension1="d0", visitor_id="a"), _visit(dimension1="d90+", visitor_id="b")])
        assert result["cohorts"]["d0"]["patrons"] == 1
        assert result["cohorts"]["d90+"]["patrons"] == 1
        assert result["cohorts"]["visitor"]["patrons"] == 0

    def test_counts_unique_patrons_not_visits(self):
        """P_tau is *unique patrons*; counting visits inflates it for repeat sessions."""
        visits = [
            _visit(dimension1="d0", visitor_id="same"),
            _visit(dimension1="d0", visitor_id="same"),
            _visit(dimension1="d0", visitor_id="other"),
        ]
        result = _gather(visits)
        assert result["cohorts"]["d0"]["patrons"] == 2
        assert result["visits"] == 3

    def test_prefers_user_id_over_visitor_id_for_identity(self):
        """A logged-in patron on two devices is one patron."""
        visits = [
            _visit(dimension1="d1+", visitor_id="deviceA", user_id="patron1"),
            _visit(dimension1="d1+", visitor_id="deviceB", user_id="patron1"),
        ]
        assert _gather(visits)["cohorts"]["d1+"]["patrons"] == 1

    def test_engagement_is_weighted_points_per_patron(self):
        visits = [
            _visit(dimension1="d0", visitor_id="a", events=[("CTAClick", "Read")]),  # 100
            _visit(dimension1="d0", visitor_id="b", events=[("MainNav", "Explore")]),  # 10
        ]
        result = _gather(visits)
        assert result["classes"]["registrant"]["weighted_total"] == 110
        assert result["classes"]["registrant"]["patrons"] == 2
        assert result["classes"]["registrant"]["engagement"] == 55.0

    def test_r_total_applies_class_weights(self):
        visits = [
            _visit(dimension1="visitor", visitor_id="v", events=[("CTAClick", "Read")]),  # 100 * 0.01 = 1
            _visit(dimension1="d0", visitor_id="r", events=[("CTAClick", "Read")]),  # 100 * 0.20 = 20
            _visit(dimension1="d1+", visitor_id="g", events=[("CTAClick", "Read")]),  # 100 * 0.50 = 50
            _visit(dimension1="d90+", visitor_id="t", events=[("CTAClick", "Read")]),  # 100 * 1.00 = 100
        ]
        result = _gather(visits)
        assert result["r_total"] == pytest.approx(171.0)
        assert result["r_per_patron"] == pytest.approx(171.0 / 4)

    def test_reports_all_seven_cohorts_even_when_empty(self):
        """Cohorts are the storage primitive; the 4 classes are a rollup on top."""
        result = _gather([])
        assert set(result["cohorts"]) == set(retention.COHORTS)
        assert set(result["classes"]) == set(retention.PATRON_CLASSES)
        assert result["r_total"] == 0.0
        assert result["r_per_patron"] == 0.0

    def test_class_totals_equal_the_sum_of_their_cohorts(self):
        visits = [
            _visit(dimension1="d1+", visitor_id="a", events=[("CTAClick", "Read")]),
            _visit(dimension1="d7+", visitor_id="b", events=[("CTAClick", "Edit")]),
            _visit(dimension1="d30+", visitor_id="c", events=[("MainNav", "Explore")]),
        ]
        result = _gather(visits)
        returning_cohorts = retention.PATRON_CLASSES["returning"]["cohorts"]
        assert result["classes"]["returning"]["patrons"] == sum(result["cohorts"][c]["patrons"] for c in returning_cohorts)
        assert result["classes"]["returning"]["weighted_total"] == sum(result["cohorts"][c]["weighted_total"] for c in returning_cohorts)

    def test_unknown_cohort_values_are_bucketed_as_visitor(self):
        result = _gather([_visit(dimension1="d999+", visitor_id="a")])
        assert result["classes"]["visitor"]["patrons"] == 1

    def test_missing_dimension1_defaults_to_visitor(self):
        result = _gather([{"visitorId": "a", "actionDetails": []}])
        assert result["cohorts"]["visitor"]["patrons"] == 1

    def test_null_dimension1_defaults_to_visitor(self):
        result = _gather([{"dimension1": None, "visitorId": "a", "actionDetails": []}])
        assert result["cohorts"]["visitor"]["patrons"] == 1

    def test_queries_the_requested_window(self):
        client = _stub_client([])
        retention.gather_retention_scores(client=client, hours=3)
        since = client.get_visits_since.call_args.args[0]
        assert 2.9 < (retention._utcnow() - since).total_seconds() / 3600 < 3.1


class TestEventBreakdown:
    def test_reports_which_events_earned_the_points(self):
        visits = [
            _visit(dimension1="d0", visitor_id="a", events=[("CTAClick", "Read")]),
            _visit(dimension1="d90+", visitor_id="b", events=[("CTAClick", "Read"), ("MainNav", "Explore")]),
        ]
        events = _gather(visits)["events"]
        assert events["read"] == {"count": 2, "points": 100, "total": 200}
        assert events["explorer_view"] == {"count": 1, "points": 10, "total": 10}

    def test_events_are_ordered_by_total_points_descending(self):
        visits = [_visit(dimension1="d0", visitor_id=str(n), events=[("MainNav", "MyBooks")]) for n in range(10)]
        visits.append(_visit(dimension1="d0", visitor_id="x", events=[("CTAClick", "Read")]))
        assert list(_gather(visits)["events"]) == ["read", "mybooks_view"]

    def test_event_totals_equal_the_overall_weighted_points(self):
        visits = [_visit(dimension1=c, visitor_id=c, events=[("CTAClick", "Read"), ("CTAClick", "Edit")]) for c in retention.COHORTS]
        result = _gather(visits)
        assert sum(e["total"] for e in result["events"].values()) == sum(c["weighted_total"] for c in result["cohorts"].values())


class TestVisitHour:
    def test_truncates_to_the_hour_the_visit_started(self):
        # 2026-07-27T14:37:11Z
        assert retention._visit_hour({"firstActionTimestamp": 1785163031}) == datetime.datetime(2026, 7, 27, 14, 0, tzinfo=datetime.UTC)

    def test_falls_back_to_server_timestamp(self):
        assert retention._visit_hour({"serverTimestamp": 1785163031}).hour == 14

    def test_returns_none_when_there_is_no_timestamp(self):
        assert retention._visit_hour({}) is None

    def test_returns_none_for_an_unparseable_timestamp(self):
        assert retention._visit_hour({"firstActionTimestamp": "not-a-number"}) is None


class TestGatherByHour:
    def _run(self, visits, hours=3):
        return retention.gather_retention_scores_by_hour(client=_stub_client(visits), hours=hours)

    def test_returns_one_bucket_per_hour_most_recent_first(self):
        buckets = self._run([], hours=3)
        assert len(buckets) == 3
        starts = [b["hour_start"] for b in buckets]
        assert starts == sorted(starts, reverse=True)

    def test_only_the_current_hour_is_flagged_partial(self):
        buckets = self._run([], hours=3)
        assert [b["partial"] for b in buckets] == [True, False, False]

    def test_visits_land_in_the_hour_they_started(self):
        now = retention._utcnow().replace(minute=0, second=0, microsecond=0)
        this_hour = int(now.timestamp()) + 60
        last_hour = int((now - datetime.timedelta(hours=1)).timestamp()) + 60
        visits = [
            _visit(dimension1="d0", visitor_id="a", timestamp=this_hour, events=[("CTAClick", "Read")]),
            _visit(dimension1="d0", visitor_id="b", timestamp=last_hour, events=[("CTAClick", "Read")]),
            _visit(dimension1="d0", visitor_id="c", timestamp=last_hour, events=[("CTAClick", "Read")]),
        ]
        buckets = self._run(visits, hours=2)
        assert buckets[0]["visits"] == 1
        assert buckets[1]["visits"] == 2

    def test_visits_outside_the_window_are_dropped(self):
        old = int((retention._utcnow() - datetime.timedelta(hours=12)).timestamp())
        buckets = self._run([_visit(dimension1="d0", visitor_id="a", timestamp=old)], hours=2)
        assert sum(b["visits"] for b in buckets) == 0

    def test_a_visit_with_no_timestamp_is_dropped_rather_than_miscounted(self):
        buckets = self._run([_visit(dimension1="d0", visitor_id="a")], hours=2)
        assert sum(b["visits"] for b in buckets) == 0

    def test_fetches_once_for_the_whole_span(self):
        client = _stub_client([])
        retention.gather_retention_scores_by_hour(client=client, hours=6)
        assert client.get_visits_since.call_count == 1

    def test_each_bucket_is_scored_as_a_one_hour_window(self):
        assert all(b["window_hours"] == 1 for b in self._run([], hours=3))


class TestRetentionGauges:
    def test_gauge_names_match_what_write_to_statsd_emits(self, monkeypatch):
        scores = _gather([_visit(dimension1="d0", visitor_id="a", events=[("CTAClick", "Read")])])
        emitted = {}
        client = Mock()
        client.gauge.side_effect = emitted.__setitem__
        monkeypatch.setattr(retention, "configure_statsd", lambda _c: client)
        retention.write_retention_to_statsd("conf.yml", scores)
        assert emitted == retention.retention_gauges(scores)

    def test_includes_the_north_star_series(self):
        gauges = retention.retention_gauges(_gather([]))
        assert "stats.ol.retention.total_score.hourly" in gauges
        assert "stats.ol.retention.per_patron.hourly" in gauges

    def test_covers_every_cohort_and_class_by_name(self):
        gauges = retention.retention_gauges(_gather([]))
        for cohort in retention.COHORTS:
            safe = retention._statsd_safe(cohort)
            assert f"stats.ol.retention.cohort.{safe}.points.hourly.total" in gauges
        for cls in retention.PATRON_CLASSES:
            assert f"stats.ol.retention.class.{cls}.points.hourly.total" in gauges

    def test_emits_data_quality_counters(self):
        """A broken feed must be visible on the dashboard, not only in a log line."""
        gauges = retention.retention_gauges(_gather([]))
        for name in ("missing_dimension", "unknown_cohort", "unidentified_patrons", "dropped_no_timestamp", "started_before_window", "truncated"):
            assert f"stats.ol.retention.quality.{name}.hourly" in gauges


class TestSanityWarnings:
    def test_warns_when_no_visits_are_returned(self):
        result = _gather([])
        assert any("no visits" in warning.lower() for warning in result["warnings"])

    def test_warns_when_a_class_has_patrons_but_zero_engagement(self):
        """Silent zeroing is exactly how both prototype bugs hid."""
        result = _gather([_visit(dimension1="d0", visitor_id="a")])
        assert any("registrant" in warning for warning in result["warnings"])

    def test_no_warnings_on_a_healthy_sample(self):
        visits = [_visit(dimension1=cohort, visitor_id=cohort, events=[("CTAClick", "Read")]) for cohort in retention.COHORTS]
        assert _gather(visits)["warnings"] == []


class TestWriteRetentionToStatsd:
    @pytest.fixture
    def emitted(self, monkeypatch):
        gauges: dict[str, float] = {}
        client = Mock()
        client.gauge.side_effect = gauges.__setitem__
        monkeypatch.setattr(retention, "configure_statsd", lambda _configfile: client)
        return gauges

    def test_emits_every_cohort_and_class_plus_the_totals(self, emitted):
        scores = _gather([_visit(dimension1="d0", visitor_id="a", events=[("CTAClick", "Read")])])
        retention.write_retention_to_statsd("conf.yml", scores)

        for cohort in retention.COHORTS:
            safe = retention._statsd_safe(cohort)
            assert f"stats.ol.retention.cohort.{safe}.patrons.hourly.total" in emitted
            assert f"stats.ol.retention.cohort.{safe}.engagement.hourly" in emitted
        for cls in retention.PATRON_CLASSES:
            assert f"stats.ol.retention.class.{cls}.patrons.hourly.total" in emitted
            assert f"stats.ol.retention.class.{cls}.engagement.hourly" in emitted
        assert emitted["stats.ol.retention.total_score.hourly"] == scores["r_total"]
        assert emitted["stats.ol.retention.per_patron.hourly"] == scores["r_per_patron"]

    def test_metric_names_never_contain_a_plus_sign(self, emitted):
        """Graphite/statsd keys must stay alphanumeric; cohorts like `d1+` need escaping."""
        retention.write_retention_to_statsd("conf.yml", _gather([]))
        assert emitted
        assert not any("+" in key for key in emitted)

    def test_statsd_safe_escapes_plus(self):
        assert retention._statsd_safe("d1+") == "d1_plus"
        assert retention._statsd_safe("visitor") == "visitor"


class TestImportIndependence:
    """Retention must stay computable without dragging Open Library in.

    The Core Vitals service is meant to run as separately from openlibrary.org
    as possible, so this module's value is partly that it has no app
    dependencies. `openlibrary/admin/vitals.py` pulls in 80+ app and infobase
    modules; if retention ever imports from there, or from anything that reaches
    the database, lifting it into the service stops being a file copy.
    """

    FORBIDDEN_PREFIXES = ("infogami", "web", "openlibrary.admin", "openlibrary.plugins", "openlibrary.core.db")

    def _fresh_import_footprint(self):

        code = "import sys, json; before=set(sys.modules);import openlibrary.core.retention;print(json.dumps(sorted(set(sys.modules)-before)))"
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
        return jsonlib.loads(out.stdout)

    def test_importing_retention_does_not_pull_in_the_app(self):
        pulled = self._fresh_import_footprint()
        offenders = [m for m in pulled if m.startswith(self.FORBIDDEN_PREFIXES)]
        assert offenders == [], f"retention.py must not import Open Library internals, found: {offenders}"

    def test_the_only_openlibrary_modules_are_retention_and_matomo(self):
        pulled = self._fresh_import_footprint()
        ol = {m for m in pulled if m.startswith("openlibrary")}
        assert ol <= {"openlibrary", "openlibrary.core", "openlibrary.core.matomo", "openlibrary.core.retention"}

    def test_matomo_client_is_also_independent(self):
        """The client moves to the service too, so it must stay clean as well."""
        source = pathlib.Path(matomo.__file__).read_text()
        assert "from openlibrary" not in source
        assert "import openlibrary" not in source


class TestPageUrlMatching:
    """Substring matching on the whole URL scored reading-log pages as book views.

    Those pages are logged-in only, so the inflation landed on the classes
    weighted 20-100x above `visitor` -- a systematic upward bias in the
    north-star number rather than noise.
    """

    @pytest.mark.parametrize(
        "url",
        [
            "https://openlibrary.org/account/books/want-to-read",
            "https://openlibrary.org/people/mek/books/already-read",
            "https://openlibrary.org/people/mek/books",
            "https://openlibrary.org/people/someone/books/currently-reading",
        ],
    )
    def test_reading_log_shelves_are_not_book_views(self, url):
        assert retention._score_page_url(url) is None

    def test_search_inside_is_not_scored_as_search(self):
        """search_inside is declared untracked; scoring it as `search` contradicts that."""
        assert retention._score_page_url("https://openlibrary.org/search/inside?q=cats") is None

    def test_a_query_string_cannot_fake_a_path(self):
        assert retention._score_page_url("https://openlibrary.org/works/OL1W/x?utm=/search") == "book_view"

    def test_a_third_party_url_scores_nothing(self):
        """Matomo should only report URLs for the tracked site, but do not rely on it."""
        assert retention._score_page_url("https://evil.example.com/works/fake") is None
        assert retention._score_page_url("https://openlibrary.org.evil.com/works/fake") is None

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://openlibrary.org/works/OL1W", "book_view"),
            ("https://openlibrary.org/books/OL1M", "book_view"),
            ("https://openlibrary.org/authors/OL1A", "author_view"),
            ("https://openlibrary.org/search?q=x", "search"),
            ("https://openlibrary.org/search/authors", "search"),
        ],
    )
    def test_real_pages_still_score(self, url, expected):
        assert retention._score_page_url(url) == expected

    def test_site_search_action_type_is_accepted(self):
        """If Matomo has search-parameter detection on, /search arrives as type='search'."""
        visit = {"dimension1": "d0", "visitorId": "a", "actionDetails": [{"type": "search", "url": "https://openlibrary.org/search?q=x"}]}
        assert retention._score_visit(visit) == {"search": 5}


class TestDataQualityDetection:
    """The historical bugs produced a smaller score, never an error. These are the
    checks that would have caught them."""

    def test_a_renamed_dimension_is_reported_not_swallowed(self):
        """Renumbering dimension1 collapsed R_total ~54x with no warning at all."""
        visits = [{"dimension2": "d90+", "visitorId": f"v{n}", "actionDetails": []} for n in range(50)]
        result = _gather(visits)
        assert result["data_quality"]["missing_dimension"] == 50
        assert any("dimension1" in w for w in result["warnings"])

    def test_relabelled_cohorts_are_reported(self):
        visits = [_visit(dimension1="d1", visitor_id=f"v{n}") for n in range(50)]
        result = _gather(visits)
        assert result["data_quality"]["unknown_cohort"] == 50
        assert any("outside" in w for w in result["warnings"])

    def test_an_all_visitor_hour_is_flagged(self):
        """Real openlibrary.org traffic always has some logged-in patrons."""
        visits = [_visit(dimension1="visitor", visitor_id=f"v{n}", events=[("CTAClick", "Read")]) for n in range(50)]
        assert any("cohort tracking may be broken" in w for w in _gather(visits)["warnings"])

    def test_a_healthy_mix_is_not_flagged(self):
        visits = [_visit(dimension1=c, visitor_id=c, events=[("CTAClick", "Read")]) for c in retention.COHORTS]
        assert _gather(visits)["warnings"] == []

    def test_unidentifiable_visits_do_not_become_one_phantom_patron(self):
        """Adding "" to the set merged 10 visits into 1 patron with 10x the engagement."""
        visits = [{"dimension1": "d90+", "actionDetails": [{"type": "event", "eventCategory": "CTAClick", "eventAction": "Read"}]} for _ in range(10)]
        result = _gather(visits)
        assert result["cohorts"]["d90+"]["patrons"] == 0
        assert result["data_quality"]["unidentified_patrons"] == 10

    def test_truncation_is_surfaced_as_a_warning(self):
        client = _stub_client([_visit(dimension1="d0", visitor_id="a")], truncated_reason="hit the page cap")
        result = retention.gather_retention_scores(client=client)
        assert any("truncated" in w for w in result["warnings"])

    def test_a_patron_in_two_cohorts_is_counted_once(self):
        visits = [_visit(dimension1="d0", visitor_id="same"), _visit(dimension1="d90+", visitor_id="same")]
        assert _gather(visits)["total_patrons"] == 1

    def test_visits_with_no_timestamp_are_counted_when_bucketing(self):
        client = _stub_client([_visit(dimension1="d0", visitor_id="a")])
        hourly = retention.gather_retention_scores_by_hour(client=client, hours=2)
        assert hourly[0]["data_quality"]["dropped_no_timestamp"] == 1
        assert any("not counted in any hour" in w for w in hourly[0]["warnings"])
