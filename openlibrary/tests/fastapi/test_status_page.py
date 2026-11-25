"""`/status` HTML page on FastAPI, and its web.py handler while that still exists.

The shell around the page is tested in `test_site_page.py`; these test the page's own body.
"""

from types import SimpleNamespace
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from openlibrary.fastapi.status import pages
from openlibrary.plugins.openlibrary import status as status_module
from openlibrary.utils.request_context import site

DEV_MERGED_OUTPUT = """\
Updating to master
---
origin pull/14668/head # Serve /search/bulk with FastAPI
 openlibrary/fastapi/search.py | 8 ++++++++
Merge made by the 'ort' strategy.
---
origin pull/14700/head # <b>Conflicting</b> change
CONFLICT (content): Merge conflict in <b>x</b>.py
Automatic merge failed; fix conflicts and then commit the result.
---
origin pull/14701/head # Pinned change
Merge conflict for PR #14701 (pinned abc1234) — skipping
---
origin master
Already up to date.
---
Done"""


@pytest.fixture
def client(site_page_app) -> TestClient:
    return TestClient(site_page_app(pages))


@pytest.fixture(autouse=True)
def maintainers(monkeypatch):
    """Only the user named `maintainer` is a maintainer."""

    def current_user():
        user = site.get().get_user()
        return user and SimpleNamespace(is_maintainer=lambda: user.key == "/people/maintainer")

    monkeypatch.setattr("openlibrary.fastapi.status.get_current_user", current_user)


@pytest.fixture
def server(monkeypatch):
    """A testing server: start-up info, a deploy log and a testing state file."""
    monkeypatch.setattr(status_module, "status_info", {"Software version": "abc1234", "Host": "ol-dev1"})
    monkeypatch.setattr(status_module, "get_dev_merged_status", lambda: status_module.DevMergedStatus.from_output(DEV_MERGED_OUTPUT))
    monkeypatch.setattr(status_module, "_load_testing_state", lambda: status_module.TestingState(last_deploy_at="", prs=[]))
    monkeypatch.setattr(status_module, "JENKINS_JOB_URL", "https://jenkins.example/job/deploy")


@pytest.fixture
def production(monkeypatch):
    """A production server: no deploy log and no testing state file."""
    monkeypatch.setattr(status_module, "status_info", {"Software version": "abc1234"})
    monkeypatch.setattr(status_module, "get_dev_merged_status", lambda: None)
    monkeypatch.setattr(status_module, "_load_testing_state", lambda: None)


def test_status_page_shows_build_and_system_info(client, server):
    response = client.get("/status")

    assert response.status_code == 200
    html = response.text
    assert "<title>Open Library server status | Open Library</title>" in html
    assert "<h1>Server status</h1>" in html
    assert '<a href="https://github.com/internetarchive/openlibrary/pull/14668">#14668: Serve /search/bulk with FastAPI</a>' in html
    assert "#14700: &lt;b&gt;Conflicting&lt;/b&gt; change" in html
    assert "<code>origin master</code>" in html  # a line with no PR number isn't linked
    assert "<pre>CONFLICT (content): Merge conflict in &lt;b&gt;x&lt;/b&gt;.py\n" in html
    # Both merge-failure messages mark the row; the merged PR and master don't.
    assert html.count('<tr class="red">') == 2
    assert html.count('<tr class="">') == 2
    assert "<th>Software version</th>" in html
    assert "<td>ol-dev1</td>" in html


def test_status_page_answers_head(client, server):
    assert client.head("/status").status_code == 200


@pytest.mark.parametrize("headers", [{}, {"x-user": "visitor"}], ids=["anonymous", "logged-in"])
def test_non_maintainers_see_the_notice_not_the_panel(client, server, headers):
    html = client.get("/status", headers=headers).text

    assert "The testing environment panel is only visible to maintainers." in html
    assert "<ol-testing-environment" not in html


def test_maintainers_see_the_testing_panel(client, server):
    html = client.get("/status", headers={"x-user": "maintainer"}).text

    assert "only visible to maintainers" not in html
    assert html.count('src="/static/build/components/production/ol-TestingEnvironment.js"') == 1
    assert '<ol-testing-environment maintainer="true" jenkins-url="https://jenkins.example/job/deploy" i18n="' in html
    i18n = html.split(' i18n="', 1)[1].split('"', 1)[0]
    assert '"title": "Testing Environment"' in unquote(i18n)


@pytest.mark.parametrize("user", ["maintainer", "visitor"])
def test_production_shows_only_system_info(client, production, user):
    html = client.get("/status", headers={"x-user": user}).text

    assert "only visible to maintainers" not in html
    assert "<ol-testing-environment" not in html
    assert "Last Build Result" not in html
    assert "<th>Software version</th>" in html


def test_status_page_does_not_read_webpy_ctx(site_page_app, server, webpy_leftovers, fetch_concurrently):
    """The page renders without web.py's request state, which a FastAPI request must not touch."""
    users = ["maintainer", "visitor"] * 4
    responses = fetch_concurrently(site_page_app(pages), [("/status", {"x-user": user}) for user in users])
    for user, response in zip(users, responses):
        assert response.status_code == 200
        assert webpy_leftovers not in response.text
        # The component's script is on every maintainer's page, not only the first one a thread renders.
        assert ("ol-TestingEnvironment.js" in response.text) == (user == "maintainer")


def test_webpy_handler_renders_the_fastapi_body(monkeypatch, client, server, request_context_fixture):
    """Until web.py's handler is retired, both servers render the same page body."""
    request_context_fixture(lang="en")
    monkeypatch.setattr(status_module, "_is_maintainer", lambda: True)
    result = status_module.status().GET()

    assert result.title == "Open Library server status"  # web.py's layout reads the title from here
    webpy_body = str(result)
    assert "<ol-testing-environment" in webpy_body
    assert webpy_body in client.get("/status", headers={"x-user": "maintainer"}).text
