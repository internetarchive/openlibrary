"""Tests for the /tasks/rows.json endpoint."""

from __future__ import annotations

from unittest.mock import patch

from openlibrary.contribute import initiatives

URL = "/tasks/rows.json"
BUILD = "openlibrary.fastapi.tasks.contribute.build_task_rows"

ROW = {
    "book": {
        "key": "/books/OL1M",
        "olid": "OL1M",
        "edit_url": "/books/OL1M/edit",
        "title": "A Book",
        "authors": "An Author",
        "cover_url": None,
        "edition_line": "A Publisher · 2001",
        "isbn13": None,
        "edition_count": 3,
        "work_key": "/works/OL1W",
        "readers": 120,
    },
    "tasks": [
        {
            "key": "OL1M/covers",
            "field": "covers",
            "label": "Cover",
            "action_label": "Add a cover",
            "url": "/tasks/task/OL1M/covers",
            "weight": 1.5,
        }
    ],
}


def test_rows_need_a_signed_in_member(fastapi_client):
    assert fastapi_client.get(URL).status_code == 401


def test_rows_answer_202_while_the_pool_builds(fastapi_client, mock_authenticated_user):
    with patch(BUILD, return_value=None):
        response = fastapi_client.get(URL)
    assert response.status_code == 202
    assert response.text == ""


def test_rows_return_the_list_as_json_for_a_normalized_filter_and_initiative(fastapi_client, mock_authenticated_user):
    with patch(BUILD, return_value=[ROW]) as build:
        response = fastapi_client.get(URL, params={"task": "not-a-filter", "initiative": "not-an-initiative"})
    assert response.status_code == 200
    assert response.json() == {"rows": [ROW]}
    assert build.call_args.args == ("", initiatives.MOST_READ)


def test_rows_draw_from_the_initiative_named(fastapi_client, mock_authenticated_user):
    with patch(BUILD, return_value=[]) as build:
        response = fastapi_client.get(URL, params={"task": "genres", "initiative": initiatives.TAGS.slug})
    assert response.json() == {"rows": []}
    assert build.call_args.args == ("genres", initiatives.TAGS)
