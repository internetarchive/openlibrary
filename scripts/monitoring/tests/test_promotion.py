from scripts.monitoring.promotion import (
    MAX_LABEL_LENGTH,
    RollingPromoter,
    parse_uniq_c,
    promoted_events,
    safe_label,
    tally,
)

BUCKET = "stats.ol-covers.bot_traffic"


def test_safe_label_sanitizes_and_bounds():
    assert safe_label("Bontent") == "Bontent"
    assert safe_label("ISBN.nu") == "ISBN_nu"
    assert safe_label("bot; rm -rf /") == "bot_rm_-rf"
    # Length is bounded, since the User-Agent it comes from is attacker-controlled.
    assert len(safe_label("x" * 500)) == MAX_LABEL_LENGTH
    # A name that sanitizes away entirely still has to produce a usable segment.
    assert safe_label("...") == "unknown"
    assert safe_label("") == "unknown"
    # `other` is reserved, so an agent cannot pollute the long-tail bucket.
    assert safe_label("other") == "other_agent"
    assert safe_label("OTHER") != "other"


def test_parse_uniq_c_skips_malformed_lines():
    assert parse_uniq_c("""
       412 semrushbot
       118 dataforseobot
        not-a-count
        7
       3 somerandomcrawler
    """) == [(412, "semrushbot"), (118, "dataforseobot"), (3, "somerandomcrawler")]

    assert parse_uniq_c("") == []


def test_tally_sums_values_that_share_a_label():
    rows = [(10, "Pinakes-POC/0.1 (SNU)"), (5, "Pinakes-POC/0.2 (SNU)"), (2, "Gleeph/1.0")]
    assert tally(rows, key=lambda ua: safe_label(ua.split()[0].split("/")[0])) == {
        "Pinakes-POC": 15,
        "Gleeph": 2,
    }


def test_below_threshold_agents_stay_in_other():
    promoter = RollingPromoter(min_count=75, max_labels=10)
    assert promoter.split({"smallbot": 10, "tinybot": 5}) == {"other": 15}


def test_agent_is_promoted_once_it_crosses_the_threshold_over_the_window():
    promoter = RollingPromoter(min_count=75, max_labels=10)

    # 10 requests a minute is far below the per-tick threshold, but it accrues.
    for tick in range(7):
        labelled = promoter.split({"steadybot": 10})
        assert labelled == {"other": 10}, f"promoted too early, on tick {tick}"

    # The 8th tick takes the window total to 80, past the floor of 75.
    assert promoter.split({"steadybot": 10}) == {"steadybot": 10, "other": 0}


def test_promotion_lapses_once_the_agent_ages_out_of_the_window():
    promoter = RollingPromoter(min_count=75, max_labels=10, window_ticks=3)

    promoter.split({"burstbot": 100})
    assert promoter.split({"burstbot": 1}) == {"burstbot": 1, "other": 0}

    # Two quiet ticks push the burst out of the 3-tick window.
    promoter.split({})
    promoter.split({})
    assert promoter.split({"burstbot": 1}) == {"other": 1}


def test_max_labels_caps_cardinality_and_keeps_the_biggest():
    promoter = RollingPromoter(min_count=10, max_labels=3)
    counts = {"a": 50, "b": 40, "c": 30, "d": 20, "e": 10}

    labelled = promoter.split(counts)

    assert set(labelled) == {"a", "b", "c", "other"}
    # The agents that lost the ranking are not dropped, they fold into other.
    assert labelled["other"] == 30
    assert sum(labelled.values()) == sum(counts.values())


def test_ranking_ties_break_deterministically():
    first = RollingPromoter(min_count=10, max_labels=2)
    second = RollingPromoter(min_count=10, max_labels=2)
    counts = {"zeta": 10, "alpha": 10, "beta": 10}

    assert first.split(counts) == second.split(dict(reversed(counts.items())))


def test_pinned_agents_bypass_the_floor_and_the_cap():
    promoter = RollingPromoter(min_count=75, max_labels=1)
    counts = {"quietpartner": 1, "loud": 500, "alsoloud": 400}

    labelled = promoter.split(counts, pinned={"quietpartner"})

    # Pinned keeps its series despite being far below the floor...
    assert labelled["quietpartner"] == 1
    # ...and does not consume the single promotion slot, which goes to the biggest.
    assert labelled["loud"] == 500
    assert labelled["other"] == 400


def test_a_loud_pinned_agent_does_not_eat_a_promotion_slot():
    # A pinned name already has a guaranteed series. If it also competes in the
    # ranking it spends a slot it does not need, and the new agents this exists
    # to find are starved -- which is the whole feature failing quietly.
    promoter = RollingPromoter(min_count=50, max_labels=2)
    counts = {"BigPinnedPartner": 1000, "NewPartnerA": 500, "NewPartnerB": 400}

    labelled = promoter.split(counts, pinned={"BigPinnedPartner"})

    assert labelled["BigPinnedPartner"] == 1000
    assert labelled["NewPartnerA"] == 500
    assert labelled["NewPartnerB"] == 400
    assert labelled["other"] == 0


def test_kept_labels_report_zero_rather_than_a_gap_when_quiet():
    # An agent at the floor sends nothing in most individual minutes. Emitting
    # no datapoint renders a stacked graph as a broken sawtooth.
    promoter = RollingPromoter(min_count=75, max_labels=10)
    promoter.split({"burstybot": 600})

    assert promoter.split({}, pinned={"QuietPartner"}) == {
        "burstybot": 0,
        "QuietPartner": 0,
        "other": 0,
    }


def test_reserved_labels_cannot_be_minted_by_an_agent():
    # utils.sh emits <bucket>.non_bot from bash; a promoted agent that minted the
    # same label would overwrite the real human-traffic count. list_unknown_bot_counts
    # already sed's non-alphanumerics to underscores, so `non-bot/1.0` arrives here
    # as `non_bot` -- that is the form the reservation has to catch.
    assert safe_label("non_bot") == "non_bot_agent"
    assert safe_label("other") == "other_agent"
    # And the reservation survives into the emitted metric path.
    promoter = RollingPromoter(min_count=1, max_labels=10)
    events = promoted_events({safe_label("non_bot"): 500}, promoter, BUCKET, timestamp=1)
    assert sorted(e.path for e in events) == [
        "stats.ol-covers.bot_traffic.non_bot_agent",
        "stats.ol-covers.bot_traffic.other",
    ]


def test_other_is_always_emitted_so_the_series_does_not_go_stale():
    promoter = RollingPromoter(min_count=1, max_labels=10)
    assert promoter.split({}) == {"other": 0}
    assert promoter.split({"bigbot": 5}) == {"bigbot": 5, "other": 0}


def test_counts_are_conserved_across_the_split():
    promoter = RollingPromoter(min_count=20, max_labels=2)
    counts = {"a": 100, "b": 50, "c": 7, "d": 3}
    assert sum(promoter.split(counts).values()) == sum(counts.values())


def test_other_metric_is_emitted_even_when_nothing_is_promoted():
    # log_recent_bot_traffic used to emit `<bucket>.other` itself, and its test
    # asserted the exact line. That emission moved here when the promotion
    # decision did, so the metric path is asserted here instead.
    promoter = RollingPromoter(min_count=75, max_labels=10)

    events = promoted_events({"smallbot": 3, "tinybot": 2}, promoter, BUCKET, timestamp=1741054377)

    assert [e.serialize_str() for e in events] == ["stats.ol-covers.bot_traffic.other 5.0 1741054377"]


def test_other_metric_is_emitted_alongside_promoted_agents():
    promoter = RollingPromoter(min_count=75, max_labels=10)

    events = promoted_events({"bigbot": 90, "smallbot": 4}, promoter, BUCKET, timestamp=1741054377)

    assert sorted(e.serialize_str() for e in events) == [
        "stats.ol-covers.bot_traffic.bigbot 90.0 1741054377",
        "stats.ol-covers.bot_traffic.other 4.0 1741054377",
    ]


def test_other_metric_is_emitted_on_a_completely_quiet_tick():
    promoter = RollingPromoter(min_count=75, max_labels=10)

    events = promoted_events({}, promoter, BUCKET, timestamp=1741054377)

    # A quiet minute must still report zero, exactly as the old `wc -l` did, or
    # the series goes stale and the dashboard shows a gap instead of a zero.
    assert [e.serialize_str() for e in events] == ["stats.ol-covers.bot_traffic.other 0.0 1741054377"]


def test_window_holds_only_the_configured_number_of_ticks():
    promoter = RollingPromoter(min_count=1, max_labels=5, window_ticks=2)
    for _ in range(5):
        promoter.observe({"bot": 1})
    assert promoter.totals() == {"bot": 2}
    assert promoter.window_ticks == 2
