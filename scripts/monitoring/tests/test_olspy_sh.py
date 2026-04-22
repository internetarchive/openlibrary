import tempfile

from scripts.monitoring.utils import bash_run


def _make_aliases(nc_path: str, pyspy_dump_path: str) -> str:
    return f"""
ps() {{
    cat scripts/monitoring/tests/sample_ps_aux.txt
}}
export -f ps

date() {{
    echo "1741054377"
}}
export -f date

nc() {{
    cat >> {nc_path}
}}
export -f nc

py-spy() {{
    cat {pyspy_dump_path}
}}
export -f py-spy
"""


def _classify_lines(lines: str) -> str:
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as input_fp:
        input_fp.write(lines)

    result = bash_run(
        f"cat {input_fp.name} | classify_workers_cur_fn",
        sources=["olspy.sh"],
        capture_output=True,
    )
    return result.stdout.strip()


def test_log_workers_cur_fn_webpy():
    with (
        tempfile.NamedTemporaryFile(mode="w", delete=False) as aliases_fp,
        tempfile.NamedTemporaryFile(mode="w", delete=False) as nc_fp,
    ):
        aliases_fp.write(_make_aliases(nc_fp.name, "scripts/monitoring/tests/sample_py_spy_webpy_dump.txt"))

    bash_run(
        "log_workers_cur_fn webpy stats.ol-covers0.workers.webpy.cur_fn",
        sources=[aliases_fp.name, "olspy.sh"],
    )

    with open(nc_fp.name) as f:
        assert f.read().strip() == "stats.ol-covers0.workers.webpy.cur_fn.db._db_execute 1 1741054377"


def test_log_workers_cur_fn_fastapi():
    with (
        tempfile.NamedTemporaryFile(mode="w", delete=False) as aliases_fp,
        tempfile.NamedTemporaryFile(mode="w", delete=False) as nc_fp,
    ):
        aliases_fp.write(_make_aliases(nc_fp.name, "scripts/monitoring/tests/sample_py_spy_fastapi_dump.txt"))

    bash_run(
        "log_workers_cur_fn fastapi stats.ol-web0.workers.fastapi.cur_fn",
        sources=[aliases_fp.name, "olspy.sh"],
    )

    with open(nc_fp.name) as f:
        assert f.read().strip() == "stats.ol-web0.workers.fastapi.cur_fn.ia.get_api_response 2 1741054377"


def test_classify_workers_cur_fn_direct_matches():
    assert (
        _classify_lines(
            """_db_execute (web/db.py:745)
get_api_response (openlibrary/core/ia.py:39)
run_solr_query (openlibrary/plugins/worksearch/code.py:352)
"""
        )
        == """db._db_execute
ia.get_api_response
solr.run_solr_query"""
    )


def test_classify_workers_cur_fn_path_based_matches():
    assert (
        _classify_lines(
            """foo (web/db.py:745)
bar (web/template.py:884)
GET (openlibrary/plugins/worksearch/code.py:123)
"""
        )
        == """db.other
webpy.template
ol.worksearch_GET"""
    )


def test_classify_workers_cur_fn_fallback_and_special_cases():
    assert (
        _classify_lines(
            """    _recv_value (memcache.py:12)
render_list_preview_image (openlibrary/coverstore/code.py:507)
something_else (totally/custom.py:1)
"""
        )
        == """memcache._recv_value
ol.render_list_preview_image
other.other"""
    )
