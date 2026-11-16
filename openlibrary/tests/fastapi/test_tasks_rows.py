"""Tests for the /tasks/rows endpoint."""

from __future__ import annotations

from unittest.mock import patch

from openlibrary.contribute import initiatives


def test_rows_need_a_signed_in_member(fastapi_client):
    assert fastapi_client.get("/tasks/rows").status_code == 401


def test_rows_answer_202_while_the_pool_builds(fastapi_client, mock_authenticated_user):
    with patch("openlibrary.fastapi.tasks.contribute.build_task_rows", return_value=None):
        response = fastapi_client.get("/tasks/rows")
    assert response.status_code == 202
    assert response.text == ""


def test_rows_render_the_list_for_a_normalized_filter_and_initiative(fastapi_client, mock_authenticated_user):
    with (
        patch("openlibrary.fastapi.tasks.contribute.build_task_rows", return_value=[]) as build,
        patch("openlibrary.fastapi.tasks.render_jinja_template", return_value="<li>row</li>") as render,
    ):
        response = fastapi_client.get("/tasks/rows", params={"task": "not-a-filter", "initiative": "not-an-initiative"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.text == "<li>row</li>"
    assert build.call_args.args == ("", initiatives.MOST_READ)
    assert render.call_args.args == ("contribute/rows.html.jinja",)
    assert render.call_args.kwargs == {"rows": []}


def test_rows_draw_from_the_initiative_named(fastapi_client, mock_authenticated_user):
    with (
        patch("openlibrary.fastapi.tasks.contribute.build_task_rows", return_value=[]) as build,
        patch("openlibrary.fastapi.tasks.render_jinja_template", return_value=""),
    ):
        fastapi_client.get("/tasks/rows", params={"task": "genres", "initiative": initiatives.TAGS.slug})
    assert build.call_args.args == ("genres", initiatives.TAGS)
