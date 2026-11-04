"""Site context initialization at script/service entry points (#13966)."""

from contextvars import Context
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import web

import infogami
from infogami import config
from infogami.utils import delegate
from openlibrary import setup
from openlibrary.admin import stats
from openlibrary.bookworm import cli
from openlibrary.solr.data_provider import DatabaseDataProvider
from openlibrary.utils.request_context import create_context_for_script, req_context, site
from scripts import affiliate_server, expire_accounts


@pytest.fixture(autouse=True)
def isolated_web_context(monkeypatch):
    # Some legacy tests replace web.ctx with a plain dict. Workers need the
    # real thread-local semantics regardless of which tests ran before them.
    context = web.utils.ThreadedDict()
    monkeypatch.setattr(web, "ctx", context)
    monkeypatch.setattr(web.webapi, "ctx", context)
    yield
    context.clear()


def stub_script_setup(monkeypatch):
    script_site = Mock()
    monkeypatch.setattr(setup, "load_config", lambda path: None)
    monkeypatch.setattr(infogami, "_setup", lambda: setattr(web.ctx, "site", script_site))
    return script_site


def test_affiliate_load_config_sets_script_context(monkeypatch, tmp_path):
    # start_server() and the gunicorn loader both go through load_config().
    script_site = stub_script_setup(monkeypatch)
    monkeypatch.setattr(config, "amazon_creators_api", {"key": "test", "secret": "test", "id": "test"}, raising=False)
    monkeypatch.setattr(affiliate_server, "AmazonCreatorsAPI", Mock())
    config_path = tmp_path / "openlibrary.yml"
    config_path.touch()

    def run():
        affiliate_server.load_config(str(config_path))
        assert site.get() is script_site
        assert req_context.get() == create_context_for_script()

    Context().run(run)


def test_stats_initializes_script_context(monkeypatch):
    script_site = stub_script_setup(monkeypatch)
    monkeypatch.setattr(infogami, "load_config", lambda path: None)
    monkeypatch.setattr(config, "infobase_config_file", None, raising=False)
    monkeypatch.setattr(config, "plugin_path", [], raising=False)

    def run():
        stats.setup_ol_config("openlibrary.yml")
        assert site.get() is script_site
        assert req_context.get() == create_context_for_script()

    Context().run(run)


def test_expire_accounts_sets_context_before_deleting(monkeypatch, tmp_path):
    script_site = stub_script_setup(monkeypatch)
    config_path = tmp_path / "openlibrary.yml"
    config_path.touch()
    monkeypatch.setenv("OL_CONFIG", str(config_path))
    called = []

    def delete_old_links():
        assert site.get() is script_site
        assert req_context.get() == create_context_for_script()
        called.append(True)

    monkeypatch.setattr(expire_accounts, "delete_old_links", delete_old_links)
    assert Context().run(expire_accounts.main) == 0
    assert called == [True]


def test_preview_sets_context_before_catalog_matching(monkeypatch, tmp_path, capsys):
    script_site = stub_script_setup(monkeypatch)
    config_path = tmp_path / "openlibrary.yml"
    config_path.touch()
    feed = SimpleNamespace(provider_name="test", url="https://example.org/feed", to_feed=lambda: None)
    monkeypatch.setattr(cli, "setup_requests", lambda: None)
    monkeypatch.setattr(cli.FeedRegistry, "all", lambda: [feed])
    monkeypatch.setattr(cli.harvest, "build_session", lambda: None)
    monkeypatch.setattr(cli.harvest, "iter_pages", lambda *args: [{"publications": [{}]}])
    monkeypatch.setattr(cli.harvest, "_parse_publication", lambda *args: ({"source_records": ["test:1"]}, None))
    called = []

    def match(record, save):
        assert site.get() is script_site
        assert req_context.get() == create_context_for_script()
        assert save is False
        called.append(record)
        return {"key": "/books/OL1M"}

    monkeypatch.setattr(cli, "load", match)
    Context().run(cli.preview_command, ol_config=str(config_path), provider="test")
    assert len(called) == 1
    assert "no answer" not in capsys.readouterr().out.lower()


def test_database_provider_initializes_script_context(monkeypatch):
    script_site = stub_script_setup(monkeypatch)
    monkeypatch.setattr(delegate, "fakeload", lambda: setattr(web.ctx, "site", script_site))
    monkeypatch.setattr("openlibrary.core.db.get_db", Mock())
    monkeypatch.setattr(web, "database", Mock())

    def run():
        provider = DatabaseDataProvider()
        assert provider.get_site() is script_site
        assert req_context.get() == create_context_for_script()

    Context().run(run)


def test_database_provider_uses_contextvar_without_web_ctx():
    def run():
        context_site = Mock()
        web.ctx.pop("site", None)
        site.set(context_site)
        provider = DatabaseDataProvider(db=Mock())
        assert provider.get_site() is context_site
        next_site = Mock()
        site.set(next_site)
        assert provider.get_site() is next_site
        explicit_site = Mock()
        assert DatabaseDataProvider(site=explicit_site, db=Mock()).get_site() is explicit_site

    Context().run(run)
