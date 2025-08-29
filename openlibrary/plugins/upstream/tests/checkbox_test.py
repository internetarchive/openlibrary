# File: openlibrary/plugins/upstream/tests/test_checkboxes.py

import pytest
from web import application, test

# Import the app entrypoint (OpenLibrary web app)
import openlibrary.plugins.upstream.account as account


@pytest.fixture
def app():
    # Minimal WSGI app to hit account routes
    urls = ("/account/create", "openlibrary.plugins.upstream.account.Account")
    return application(urls, globals())


def test_account_create_form_contains_checkboxes(app):
    """
    Ensure that the rendered account creation page contains
    the required checkboxes as plain HTML.
    """
    response = test.app(app).get("/account/create")
    html = response.data.decode("utf-8")

    assert '<input type="checkbox" name="ia_newsletter"' in html
    assert '<input type="checkbox" name="pd_request"' in html


def test_account_create_form_submits_with_newsletter(app, monkeypatch):
    """
    Ensure that submitting the form with ia_newsletter checked
    passes notifications to InternetArchiveAccount.create().
    """
    created_args = {}

    def fake_create(**kwargs):
        created_args.update(kwargs)
        return True

    monkeypatch.setattr(account.InternetArchiveAccount, "create", fake_create)

    data = dict(
        username="testuser",
        email="test@example.com",
        password="secret",
        ia_newsletter="on"
    )

    response = test.app(app).post("/account/create", data)
    assert response.status == "200 OK"
    assert "ml_best_of" in created_args["notifications"]
    assert "ml_updates" in created_args["notifications"]


def test_account_create_form_submits_without_newsletter(app, monkeypatch):
    """
    Ensure that submitting the form WITHOUT ia_newsletter
    does not set any notifications.
    """
    created_args = {}

    def fake_create(**kwargs):
        created_args.update(kwargs)
        return True

    monkeypatch.setattr(account.InternetArchiveAccount, "create", fake_create)

    data = dict(
        username="testuser2",
        email="test2@example.com",
        password="secret",
    )

    response = test.app(app).post("/account/create", data)
    assert response.status == "200 OK"
    assert created_args["notifications"] == []
