import tempfile

from scripts.monitoring.utils import bash_run


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
            "log_recent_bot_traffic stats.ol-covers0.bot_traffic openlibrary-covers_nginx-1",
            sources=["../obfi.sh", aliases_fp.name, "utils.sh"],
        )

        with open(nc_fp.name) as f:
            # FIXME: eg gptbot is counted twice since it appears twice in each log entry
            expected_output = """
stats.ol-covers0.bot_traffic.gptbot 2 1741054377
stats.ol-covers0.bot_traffic.meta_externalagent 1 1741054377
stats.ol-covers0.bot_traffic.other 0 1741054377
stats.ol-covers0.bot_traffic.non_bot 5 1741054377
            """.strip()
            assert f.read().strip() == expected_output


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
