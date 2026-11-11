"""The main plugin must use the current site even without web.py's site."""

import gzip
import json
from unittest.mock import Mock

import pytest
import web

from infogami import config
from infogami.core import code as infogami_code
from infogami.utils import delegate, template
from openlibrary.mocks.mock_infobase import MockSite
from openlibrary.plugins.openlibrary import code, opds
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


def test_sampledump_reads_current_site(current_site, capsys):
    current_site.quicksave("/b/OL1M", "/type/edition", title="Sample book")
    current_site.quicksave("/scan/1", "/type/scan_record", title="Sample scan")

    code.sampledump()

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert {record["key"]: record["title"] for record in records} == {
        "/b/OL1M": "Sample book",
        "/scan/1": "Sample scan",
    }


@pytest.mark.parametrize("compressed", [False, True])
def test_sampleload_writes_current_site(current_site, tmp_path, compressed):
    path = tmp_path / ("sample.json.gz" if compressed else "sample.json")
    data = json.dumps({"key": "/books/OL1M", "type": {"key": "/type/edition"}, "title": "Loaded book"}).encode()
    path.write_bytes(gzip.compress(data) if compressed else data)

    code.sampleload(str(path))

    assert current_site.get("/books/OL1M").title == "Loaded book"
    assert current_site.changesets[-1]["kind"] == "infogami-sampleload-action"


def test_addbook_get_uses_current_site(current_site, monkeypatch):
    current_site.quicksave("/authors/OL1A", "/type/author", name="Test author")
    monkeypatch.setattr(web, "input", lambda: web.storage(author="/authors/OL1A"))
    render = Mock()
    monkeypatch.setattr(code, "render", render)

    assert code.addbook().GET() is render.edit.return_value

    page, path, title = render.edit.call_args.args
    assert page._site is current_site
    assert page.type.key == "/type/edition"
    assert page.authors[0].name == "Test author"
    assert (path, title) == ("/addbook", "Add Book")


def test_addbook_post_allocates_key_on_current_site(current_site, monkeypatch):
    edit = Mock()
    monkeypatch.setattr(infogami_code, "edit", edit)

    assert code.addbook().POST() is edit.return_value.POST.return_value

    edit.return_value.POST.assert_called_once_with("/books/OL1M")
    assert current_site.keys["edition"] == 1
    assert web.ctx.path == "/books/OL1M"


def test_addauthor_saves_to_current_site(current_site, monkeypatch):
    monkeypatch.setattr(code, "get_current_user", lambda: web.storage(key="/people/alice"))
    monkeypatch.setattr(web, "input", lambda *args: web.storage(name="Test author"))

    with pytest.raises(web.HTTPError) as response:
        code.addauthor().POST()

    assert web.ctx.status == "200 OK"
    assert response.value.data == "/authors/OL1A"
    assert current_site.get("/authors/OL1A").name == "Test author"
    assert current_site.changesets[-1]["kind"] == "create-author"
    assert current_site.changesets[-1]["comment"] == "New Author"


def test_clonebook_reads_current_site(current_site, monkeypatch):
    current_site.quicksave("/books/OL1M", "/type/edition", title="Original", isbn_10=["1234567890"])
    monkeypatch.setattr(web, "input", lambda *args: web.storage(key="/books/OL1M"))
    render = Mock()
    monkeypatch.setattr(code, "render", render)

    assert code.clonebook().GET() is render.edit.return_value

    page, path, title = render.edit.call_args.args
    assert page._site is current_site
    assert page.title == "Original"
    assert "isbn_10" not in page._getdata()
    assert (path, title) == ("/addbook", "Clone Book")


def test_widget_reads_current_site(current_site, monkeypatch):
    current_site.quicksave("/books/OL1M", "/type/edition", title="Widget book", authors=[])
    availability = {"OL1M": {"status": "open"}}
    monkeypatch.setattr(code, "get_availability", lambda *args: availability)
    render = Mock(return_value="widget html")
    monkeypatch.setattr(code, "render_template", render)

    result = code.widget().GET("/books/OL1M")

    assert result.rawtext == "widget html"
    name, item = render.call_args.args
    assert name == "widget"
    assert item._site is current_site
    assert item.title == "Widget book"
    assert item["availability"] == availability["OL1M"]


@pytest.mark.parametrize(
    ("identifier", "value", "record"),
    [
        ("oclc", "123_456", {"oclc_numbers": ["123 456"]}),
        ("lccn", "123", {"lccn": ["123"]}),
        ("ia", "test_item", {"ocaid": "test_item"}),
        ("ia", "test_item", {"source_records": ["ia:test_item"]}),
        ("ia", "test_item", {"type": "/type/volume", "ia_id": "test_item"}),
    ],
)
def test_bookpage_redirect_uses_current_site(current_site, monkeypatch, identifier, value, record):
    current_site.quicksave("/books/OL1M", **{"type": "/type/edition", **record})
    monkeypatch.setitem(web.ctx, "path", f"/{identifier}/{value}.json")
    monkeypatch.setitem(web.ctx, "encoding", "json")
    monkeypatch.setitem(web.ctx.env, "QUERY_STRING", "test=1")

    response = code.bookpage().GET(identifier, value)

    assert isinstance(response, web.HTTPError)
    assert web.ctx.status == "302 Found"
    assert dict(web.ctx.headers)["Location"] == "http://openlibrary.org/books/OL1M.json?test=1"


@pytest.mark.parametrize("mode", [code.rdf, code.opds, code.marcxml])
def test_export_reads_current_site(current_site, monkeypatch, mode):
    current_site.quicksave("/books/OL1M", "/type/edition", title="Export book")
    serialize = Mock(return_value="exported book")
    if mode is code.opds:
        entry = Mock()
        entry.return_value.to_string.return_value = "exported book"
        monkeypatch.setattr(opds, "OPDSEntry", entry)
        serialize = entry
    else:
        monkeypatch.setattr(template, "typetemplate", lambda name: serialize)

    result = mode().GET("/books/OL1M")

    assert result.rawtext == "exported book"
    page = serialize.call_args.args[0]
    assert page._site is current_site
    assert page.title == "Export book"


@pytest.mark.parametrize("mode", [code.rdf, code.opds, code.marcxml])
def test_export_missing_record_is_not_found(current_site, mode):
    with pytest.raises(web.HTTPError, match="404 Not Found"):
        mode().GET("/books/OL999M")

    assert web.ctx.status == "404 Not Found"


def test_yaml_edit_saves_to_current_site(current_site, monkeypatch):
    monkeypatch.setattr(delegate.context, "user", Mock(is_super_librarian_or_higher=lambda: True))
    monkeypatch.setattr(
        web,
        "input",
        lambda **kwargs: web.storage(body="key: /books/OL1M\ntype:\n  key: /type/edition\ntitle: YAML book", _comment="Update title", _save="Save"),
    )

    with pytest.raises(web.HTTPError, match="303 See Other"):
        code._yaml_edit().POST("/books/OL1M")

    assert web.ctx.status == "303 See Other"
    assert dict(web.ctx.headers)["Location"] == "http://openlibrary.org/books/OL1M.yml"
    assert current_site.get("/books/OL1M").title == "YAML book"
    assert current_site.changesets[-1]["kind"] == "edit-yaml"
    assert current_site.changesets[-1]["comment"] == "Update title"


@pytest.mark.parametrize("grant", ["api", "admin", "bot", None])
def test_can_write_uses_current_site_permissions(current_site, monkeypatch, grant):
    monkeypatch.setattr(delegate.context, "user", web.storage(key="/people/alice"))
    if grant in {"api", "admin"}:
        current_site.quicksave(f"/usergroup/{grant}", members=[{"key": "/people/alice"}])
    elif grant == "bot":
        current_site.store["account/alice"] = {"type": "account", "username": "alice", "bot": "true"}
    if grant is None and (legacy := web.ctx.get("site")):
        # A stale site's grant must not authorize this request.
        legacy.quicksave("/usergroup/api", members=[{"key": "/people/alice"}])

    assert code.can_write() is (grant is not None)


@pytest.mark.parametrize("bulk", [False, True])
def test_new_api_saves_to_current_site(current_site, monkeypatch, bulk):
    current_site.quicksave("/usergroup/api", members=[{"key": "/people/alice"}])
    monkeypatch.setattr(delegate.context, "user", web.storage(key="/people/alice"))
    queries = [{"type": "/type/edition", "title": "New book"}, {"type": {"key": "/type/author"}, "name": "New author"}]
    monkeypatch.setattr(web, "data", lambda: json.dumps(queries if bulk else queries[0]).encode())
    monkeypatch.setattr(code.api, "get_custom_headers", lambda: {"comment": "Create records", "action": "test-create"})

    keys = json.loads(code.new().POST())

    assert keys == (["/books/OL1M", "/authors/OL1A"] if bulk else "/books/OL1M")
    assert current_site.get("/books/OL1M").title == "New book"
    if bulk:
        assert current_site.get("/authors/OL1A").name == "New author"
    assert current_site.changesets[-1]["comment"] == "Create records"
    assert current_site.changesets[-1]["kind"] == "test-create"


def test_new_api_rejects_stale_site_permission(current_site, monkeypatch):
    monkeypatch.setattr(delegate.context, "user", web.storage(key="/people/alice"))
    if legacy := web.ctx.get("site"):
        legacy.quicksave("/usergroup/api", members=[{"key": "/people/alice"}])
    read_body = Mock()
    monkeypatch.setattr(web, "data", read_body)

    with pytest.raises(code.Forbidden):
        code.new().POST()

    read_body.assert_not_called()
    assert current_site.get("/books/OL1M") is None


@pytest.mark.parametrize("bulk", [False, True])
def test_invalidate_passes_current_site_to_hooks(current_site, monkeypatch, bulk):
    data = [{"key": "/books/OL1M", "title": "Updated book"}, {"key": "/authors/OL1A", "name": "Updated author"}]
    monkeypatch.setattr(code, "local_ip", "127.0.0.1")
    monkeypatch.setitem(web.ctx, "ip", "127.0.0.1")
    monkeypatch.setattr(web, "data", lambda: json.dumps(data if bulk else data[0]).encode())
    run_hooks = Mock()
    monkeypatch.setattr(code.client, "_run_hooks", run_hooks)

    result = code.invalidate().POST()

    assert result.rawtext == "ok"
    assert run_hooks.call_count == (2 if bulk else 1)
    for call, record in zip(run_hooks.call_args_list, data):
        event, thing = call.args
        assert event == "on_new_version"
        assert thing._site is current_site
        assert thing.key == record["key"]
        assert thing.get("title") == record.get("title")
