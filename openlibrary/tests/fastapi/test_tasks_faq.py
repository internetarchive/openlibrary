"""/tasks/faq on FastAPI: open to visitors, with an anchor for each question the task pages link to."""

import pytest
from fastapi.testclient import TestClient

from openlibrary.fastapi import tasks


@pytest.fixture
def client(site_page_app, monkeypatch):
    monkeypatch.setattr("openlibrary.fastapi.shared.site_page.load_shell_user", lambda: None)
    return TestClient(site_page_app(tasks.public_pages), follow_redirects=False)


def test_a_visitor_can_read_it(client):
    response = client.get("/tasks/faq")
    assert response.status_code == 200
    assert "Questions about Tasks" in response.text


@pytest.mark.parametrize("anchor", ["edition-or-work", "skip-or-not-found", "does-not-exist"])
def test_each_linked_question_has_its_anchor(client, anchor):
    assert f'id="{anchor}"' in client.get("/tasks/faq").text
