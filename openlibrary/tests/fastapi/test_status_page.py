"""`/status` HTML page on FastAPI, and its web.py handler while that still exists."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from openlibrary.fastapi.status import pages
from openlibrary.plugins.openlibrary import status as status_module
from openlibrary.utils.request_context import site

DEV_MERGED_OUTPUT = """\
Updating to master
---
origin pull/14668/head # <b>Bulk</b> search
Merge made by the 'ort' strategy.
---
origin pull/14701/head # Status page
Merge conflict for PR #14701 (pinned abc1234) — skipping
---
origin master
Already up to date.
---
Done"""


@pytest.fixture
def client(site_page_app, monkeypatch) -> TestClient:
    """A testing server, where only the user named `maintainer` is a maintainer."""
    monkeypatch.setattr(status_module, "status_info", {"Host": "ol-dev1"})
    monkeypatch.setattr(status_module, "get_dev_merged_status", lambda: status_module.DevMergedStatus.from_output(DEV_MERGED_OUTPUT))
    monkeypatch.setattr(status_module, "_load_testing_state", lambda: status_module.TestingState(last_deploy_at="", prs=[]))

    def current_user():
        user = site.get().get_user()
        return user and SimpleNamespace(is_maintainer=lambda: user.key == "/people/maintainer")

    monkeypatch.setattr("openlibrary.fastapi.status.get_current_user", current_user)
    return TestClient(site_page_app(pages))


def test_maintainers_see_build_result_and_panel(client):
    html = client.get("/status", headers={"x-user": "maintainer"}).text

    assert "<title>Open Library server status | Open Library</title>" in html
    assert '<a href="https://github.com/internetarchive/openlibrary/pull/14668">#14668: &lt;b&gt;Bulk&lt;/b&gt; search</a>' in html
    assert "<code>origin master</code>" in html
    assert html.count('<tr class="red">') == 1
    assert "<td>ol-dev1</td>" in html
    assert '<ol-testing-environment maintainer="true"' in html


@pytest.mark.parametrize("headers", [{}, {"x-user": "visitor"}])
def test_others_see_a_notice_instead_of_the_panel(client, headers):
    html = client.get("/status", headers=headers).text

    assert "only visible to maintainers" in html
    assert "<ol-testing-environment" not in html


def test_production_shows_only_system_info(client, monkeypatch):
    monkeypatch.setattr(status_module, "get_dev_merged_status", lambda: None)
    monkeypatch.setattr(status_module, "_load_testing_state", lambda: None)
    html = client.get("/status", headers={"x-user": "maintainer"}).text

    assert "Last Build Result" not in html
    assert "maintainers" not in html
    assert "<td>ol-dev1</td>" in html


def test_status_page_does_not_read_webpy_ctx(client, webpy_leftovers, fetch_concurrently):
    users = ["maintainer", "visitor"] * 4
    responses = fetch_concurrently(client.app, [("/status", {"x-user": user}) for user in users])
    for user, response in zip(users, responses):
        assert webpy_leftovers not in response.text
        # The component's script is on every maintainer's page, not only the first one a thread renders.
        assert ("ol-TestingEnvironment.js" in response.text) == (user == "maintainer")


def test_webpy_handler_renders_the_fastapi_body(client, monkeypatch, request_context_fixture):
    request_context_fixture(lang="en")
    monkeypatch.setattr(status_module, "_is_maintainer", lambda: True)
    result = status_module.status().GET()

    assert result.title == "Open Library server status"  # web.py's layout reads the title from here
    assert str(result) in client.get("/status", headers={"x-user": "maintainer"}).text
