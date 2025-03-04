from scripts.monitoring.utils import bash_run
import tempfile


def test_bash_run():
    # Test without sources
    output = bash_run("echo 'Hello, World!'", capture_output=True)
    assert output.stdout.strip() == "Hello, World!"

    # Test with sources
    with (
        tempfile.NamedTemporaryFile(mode='w', delete_on_close=False) as source1,
        tempfile.NamedTemporaryFile(mode='w', delete_on_close=False) as source2,
    ):
        source1.write("export VAR1=source1")
        source2.write("export VAR2=source2")
        source1.close()
        source2.close()

        output = bash_run(
            f"echo $VAR1 $VAR2",
            sources=[source1.name, source2.name],
            capture_output=True,
        )
        assert output.stdout.strip() == "source1 source2"


def test_log_recent_bot_traffic():
    with (
        tempfile.NamedTemporaryFile(mode='w', delete_on_close=False) as aliases_fp,
        tempfile.NamedTemporaryFile(delete_on_close=False) as nc_fp,
    ):
        # alias the docker command to return some noise
        aliases_fp.write(
            f"""
                docker() {{
                    cat scripts/monitoring/tests/sample_covers_nginx_logs.log
                }}
                export -f docker

                nc() {{
                    # Read stdin and write to nc_fp
                    cat >> {nc_fp.name}
                }}
                export -f nc

                date() {{
                    echo "1741054377"
                }}
            """
        )
        aliases_fp.close()
        nc_fp.close()

        bash_run(
            f"log_recent_bot_traffic stats.ol-covers0.bot_traffic openlibrary-covers_nginx-1",
            sources=[aliases_fp.name, "utils.sh"],
        )

        with open(nc_fp.name) as f:
            expected_output = """
stats.ol-covers0.bot_traffic.gptbot 2 1741054377
stats.ol-covers0.bot_traffic.other 0 1741054377
stats.ol-covers0.bot_traffic.non_bot 6 1741054377
            """.strip()
            assert f.read().strip() == expected_output


def test_log_recent_http_statuses():
    with (
        tempfile.NamedTemporaryFile(mode='w', delete_on_close=False) as aliases_fp,
        tempfile.NamedTemporaryFile(delete_on_close=False) as nc_fp,
    ):
        # alias the docker command to return some noise
        aliases_fp.write(
            f"""
                docker() {{
                    cat scripts/monitoring/tests/sample_covers_nginx_logs.log
                }}
                export -f docker

                nc() {{
                    # Read stdin and write to nc_fp
                    cat >> {nc_fp.name}
                }}
                export -f nc

                date() {{
                    echo "1741054377"
                }}
            """
        )
        aliases_fp.close()
        nc_fp.close()

        bash_run(
            f"log_recent_http_statuses stats.ol-covers.http_status openlibrary-covers_nginx-1",
            sources=[aliases_fp.name, "utils.sh"],
        )

        with open(nc_fp.name) as f:
            expected_output = """
stats.ol-covers.http_status.http_302 5 1741054377
stats.ol-covers.http_status.http_200 2 1741054377
            """.strip()
            assert f.read().strip() == expected_output
