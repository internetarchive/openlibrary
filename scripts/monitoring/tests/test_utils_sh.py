import tempfile

from scripts.monitoring.promotion import (
    RollingPromoter,
    parse_uniq_c,
    promoted_events,
    safe_label,
    tally,
)
from scripts.monitoring.utils import bash_run


def _unknown_bot_counts(fixture: str) -> str:
    """Run list_unknown_bot_counts against a log fixture."""
    with tempfile.NamedTemporaryFile(mode="w", delete_on_close=False) as aliases_fp:
        aliases_fp.write(f"""
                obfi_in_docker() {{
                    cat {fixture}
                }}
                export -f obfi_in_docker
            """)
        aliases_fp.close()

        return bash_run(
            "list_unknown_bot_counts",
            sources=["../obfi.sh", aliases_fp.name, "utils.sh"],
            capture_output=True,
        ).stdout


def test_bash_run():
    # Test without sources
    output = bash_run("echo 'Hello, World!'", capture_output=True)
    assert output.stdout.strip() == "Hello, World!"

    # Test with sources
    with (
        tempfile.NamedTemporaryFile(mode="w", delete_on_close=False) as source1,
        tempfile.NamedTemporaryFile(mode="w", delete_on_close=False) as source2,
    ):
        source1.write("export VAR1=source1")
        source2.write("export VAR2=source2")
        source1.close()
        source2.close()

        output = bash_run(
            "echo $VAR1 $VAR2",
            sources=[source1.name, source2.name],
            capture_output=True,
        )
        assert output.stdout.strip() == "source1 source2"


def test_log_recent_bot_traffic():
    with (
        tempfile.NamedTemporaryFile(mode="w", delete_on_close=False) as aliases_fp,
        tempfile.NamedTemporaryFile(delete_on_close=False) as nc_fp,
    ):
        # alias the obfi commands to return some noise
        aliases_fp.write(f"""
                obfi_in_docker() {{
                    cat scripts/monitoring/tests/sample_covers_nginx_logs.log
                }}
                export -f obfi_in_docker

                nc() {{
                    # Read stdin and write to nc_fp
                    cat >> {nc_fp.name}
                }}
                export -f nc

                date() {{
                    echo "1741054377"
                }}
            """)
        aliases_fp.close()
        nc_fp.close()

        bash_run(
            "log_recent_bot_traffic stats.ol-covers.bot_traffic openlibrary-covers_nginx-1",
            sources=["../obfi.sh", aliases_fp.name, "utils.sh"],
        )

        with open(nc_fp.name) as f:
            # FIXME: eg gptbot is counted twice since it appears twice in each log entry
            # `other` is no longer emitted here; monitor.py submits it alongside the
            # unknown bots it promotes. See test_list_unknown_bot_counts.
            expected_output = """
stats.ol-covers.bot_traffic.gptbot 2 1741054377
stats.ol-covers.bot_traffic.meta_externalagent 1 1741054377
stats.ol-covers.bot_traffic.non_bot 5 1741054377
            """.strip()
            assert f.read().strip() == expected_output


def test_list_unknown_bot_counts():
    output = _unknown_bot_counts("scripts/monitoring/tests/sample_unknown_bots_nginx_logs.log")

    # GPTBot is in obfi_grep_bots' list so it is counted as its own series by
    # log_recent_bot_traffic, and the plain browser UA is not a bot at all;
    # neither should show up here. Hyphens are normalized to underscores, as
    # obfi_top_bots does for the built-in names.
    counts = [line.split() for line in output.strip().split("\n")]
    assert counts == [
        ["3", "somerandomcrawler"],
        ["2", "evilspider"],
        ["1", "data_harvester_bot"],
    ]


def test_unknown_bots_still_produce_an_other_metric():
    """End-to-end cover for the `<bucket>.other` line log_recent_bot_traffic used to emit.

    The bash side now only reports names; monitor.py turns them into metrics. This
    walks that whole path so the metric cannot silently stop being submitted.
    """
    promoter = RollingPromoter(min_count=75, max_labels=25)

    output = _unknown_bot_counts("scripts/monitoring/tests/sample_unknown_bots_nginx_logs.log")
    events = promoted_events(
        tally(parse_uniq_c(output), key=safe_label),
        promoter,
        "stats.ol-covers.bot_traffic",
        timestamp=1741054377,
    )

    # None of the fixture's bots are anywhere near the threshold, so they all
    # aggregate: 3 + 2 + 1.
    assert [e.serialize_str() for e in events] == ["stats.ol-covers.bot_traffic.other 6.0 1741054377"]


def test_a_log_with_no_unknown_bots_still_produces_an_other_metric():
    # The original fixture has no unknown bots, which is why the old test asserted
    # `...bot_traffic.other 0`. bash_run uses `set -e`, so an empty pipeline here
    # would also take down the whole job on any quiet minute.
    promoter = RollingPromoter(min_count=75, max_labels=25)

    output = _unknown_bot_counts("scripts/monitoring/tests/sample_covers_nginx_logs.log")
    events = promoted_events(
        tally(parse_uniq_c(output), key=safe_label),
        promoter,
        "stats.ol-covers.bot_traffic",
        timestamp=1741054377,
    )

    assert output.strip() == ""
    assert [e.serialize_str() for e in events] == ["stats.ol-covers.bot_traffic.other 0.0 1741054377"]


def test_log_recent_http_statuses():
    with (
        tempfile.NamedTemporaryFile(mode="w", delete_on_close=False) as aliases_fp,
        tempfile.NamedTemporaryFile(delete_on_close=False) as nc_fp,
    ):
        # alias the obfi commands to return some noise
        aliases_fp.write(f"""
                obfi_in_docker() {{
                    cat scripts/monitoring/tests/sample_covers_nginx_logs.log
                }}
                export -f obfi_in_docker

                nc() {{
                    # Read stdin and write to nc_fp
                    cat >> {nc_fp.name}
                }}
                export -f nc

                date() {{
                    echo "1741054377"
                }}
            """)
        aliases_fp.close()
        nc_fp.close()

        bash_run(
            "log_recent_http_statuses stats.ol-covers.http_status openlibrary-covers_nginx-1",
            sources=["../obfi.sh", aliases_fp.name, "utils.sh"],
        )

        with open(nc_fp.name) as f:
            expected_output = """
stats.ol-covers.http_status.http_302 5 1741054377
stats.ol-covers.http_status.http_200 2 1741054377
            """.strip()
            assert f.read().strip() == expected_output


def test_log_top_response_times():
    with (
        tempfile.NamedTemporaryFile(mode="w", delete_on_close=False) as aliases_fp,
        tempfile.NamedTemporaryFile(delete_on_close=False) as nc_fp,
    ):
        aliases_fp.write(f"""
                obfi_in_docker() {{
                    cat scripts/monitoring/tests/sample_covers_nginx_logs.log
                }}
                export -f obfi_in_docker

                nc() {{
                    # Read stdin and write to nc_fp
                    cat >> {nc_fp.name}
                }}
                export -f nc

                date() {{
                    echo "1741054377"
                }}
            """)
        aliases_fp.close()
        nc_fp.close()

        bash_run(
            "log_top_response_times stats.ol-covers.response_times",
            sources=["../obfi.sh", aliases_fp.name, "utils.sh"],
        )

        with open(nc_fp.name) as f:
            expected_output = """
stats.ol-covers.response_times.10ms 1 1741054377
stats.ol-covers.response_times.100ms 3 1741054377
stats.ol-covers.response_times.1000ms 1 1741054377
stats.ol-covers.response_times.5000ms 1 1741054377
stats.ol-covers.response_times.10000ms 1 1741054377
stats.ol-covers.response_times.20000ms 0 1741054377
stats.ol-covers.response_times.LONG 0 1741054377
            """.strip()
            assert f.read().strip() == expected_output
