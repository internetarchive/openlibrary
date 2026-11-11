"""The main plugin must use the current site even without web.py's site."""

import json
from unittest.mock import Mock

import pytest
import web

from infogami import config
from infogami.utils import delegate, template
from openlibrary.mocks.mock_infobase import MockSite
from openlibrary.plugins.openlibrary import code
from openlibrary.utils.request_context import site


@pytest.fixture(params=["missing", "different"])
def current_site(mock_site, monkeypatch, request):
    """Separate the ContextVar from the legacy site, which normal mocks share."""
    token = site.set(mock_site)
    if request.param == "missing":
        monkeypatch.delitem(web.ctx, "site")
    else:
        monkeypatch.setitem(web.ctx, "site", MockSite())
    monkeypatch.setitem(web.ctx, "home", "http://openlibrary.org")
    monkeypatch.setitem(web.ctx, "path", "/")
    monkeypatch.setitem(web.ctx, "encoding", None)
    monkeypatch.setitem(config.infobase, "user_root", "/people")
    monkeypatch.setattr(delegate.context, "user", None, raising=False)
    yield mock_site
    site.reset(token)


def test_sample_actions_use_current_site(current_site, tmp_path, capsys):
    path = tmp_path / "sample.json"
    path.write_text(json.dumps({"key": "/b/OL1M", "type": {"key": "/type/edition"}, "title": "Sample book"}))

    code.sampleload(str(path))
    code.sampledump()

    assert current_site.get("/b/OL1M").title == "Sample book"
    assert current_site.changesets[-1]["kind"] == "infogami-sampleload-action"
    assert '"title": "Sample book"' in capsys.readouterr().out


def test_addauthor_saves_to_current_site(current_site, monkeypatch):
    monkeypatch.setattr(code, "get_current_user", lambda: web.storage(key="/people/alice"))
    monkeypatch.setattr(web, "input", lambda *args: web.storage(name="Test author"))

    with pytest.raises(web.HTTPError) as response:
        code.addauthor().POST()

    assert response.value.data == "/authors/OL1A"
    assert current_site.get("/authors/OL1A").name == "Test author"
    assert current_site.changesets[-1]["kind"] == "create-author"


def test_bookpage_redirect_uses_current_site(current_site, monkeypatch):
    current_site.quicksave("/books/OL1M", "/type/edition", oclc_numbers=["123 456"])
    monkeypatch.setitem(web.ctx, "path", "/oclc/123_456")

    assert isinstance(code.bookpage().GET("oclc", "123_456"), web.HTTPError)
    assert dict(web.ctx.headers)["Location"] == "http://openlibrary.org/books/OL1M"


def test_export_reads_current_site(current_site, monkeypatch):
    current_site.quicksave("/books/OL1M", "/type/edition", title="Export book")
    serialize = Mock(return_value="exported book")
    monkeypatch.setattr(template, "typetemplate", lambda name: serialize)

    assert code.rdf().GET("/books/OL1M").rawtext == "exported book"
    assert serialize.call_args.args[0].title == "Export book"


def test_yaml_edit_saves_to_current_site(current_site, monkeypatch):
    monkeypatch.setattr(delegate.context, "user", Mock(is_super_librarian_or_higher=lambda: True))
    body = "key: /books/OL1M\ntype:\n  key: /type/edition\ntitle: YAML book"
    monkeypatch.setattr(web, "input", lambda **kwargs: web.storage(body=body, _comment="Update title", _save="Save"))

    with pytest.raises(web.HTTPError, match="303 See Other"):
        code._yaml_edit().POST("/books/OL1M")

    assert current_site.get("/books/OL1M").title == "YAML book"
    assert current_site.changesets[-1]["kind"] == "edit-yaml"


def test_new_api_checks_and_saves_to_current_site(current_site, monkeypatch):
    # Permission comes from the current site's api usergroup, not the legacy site's.
    current_site.quicksave("/usergroup/api", members=[{"key": "/people/alice"}])
    monkeypatch.setattr(delegate.context, "user", web.storage(key="/people/alice"))
    monkeypatch.setattr(web, "data", lambda: json.dumps({"type": "/type/edition", "title": "New book"}).encode())
    monkeypatch.setattr(code.api, "get_custom_headers", lambda: {"comment": "Create records", "action": "test-create"})

    assert json.loads(code.new().POST()) == "/books/OL1M"
    assert current_site.get("/books/OL1M").title == "New book"
    assert current_site.changesets[-1]["kind"] == "test-create"


def test_invalidate_passes_current_site_to_hooks(current_site, monkeypatch):
    monkeypatch.setattr(code, "local_ip", "127.0.0.1")
    monkeypatch.setitem(web.ctx, "ip", "127.0.0.1")
    monkeypatch.setattr(web, "data", lambda: json.dumps({"key": "/books/OL1M", "title": "Updated book"}).encode())
    run_hooks = Mock()
    monkeypatch.setattr(code.client, "_run_hooks", run_hooks)

    assert code.invalidate().POST().rawtext == "ok"
    event, thing = run_hooks.call_args.args
    assert event == "on_new_version"
    assert thing._site is current_site
