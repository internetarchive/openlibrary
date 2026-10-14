"""Tests for the show-marc record cache (internetarchive/openlibrary#13874).

Self-contained: stubs the infobase-only modules so the view helpers load
without the full Open Library environment.
"""

import importlib.util
import json
import os
import sys
import types
from base64 import b64encode
from unittest.mock import MagicMock

import pytest
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OPENLIBRARY_DIR = os.path.dirname(os.path.dirname(HERE))
REPO_ROOT = os.path.dirname(OPENLIBRARY_DIR)
VIEWS_DIR = os.path.join(OPENLIBRARY_DIR, "views")


def _pkg(name, path):
    module = types.ModuleType(name)
    module.__path__ = [path]
    sys.modules[name] = module
    return module


_pkg("openlibrary", OPENLIBRARY_DIR)
_pkg("openlibrary.views", VIEWS_DIR)
_pkg("openlibrary.core", os.path.join(OPENLIBRARY_DIR, "core"))
_pkg("openlibrary.utils", os.path.join(OPENLIBRARY_DIR, "utils"))

_web = types.ModuleType("web")
_web.seeother = lambda url: (_ for _ in ()).throw(Exception(url))
sys.modules["web"] = _web

_app = types.ModuleType("openlibrary.app")


class _View:
    def __init_subclass__(cls, **kwargs):
        pass


_app.view = _View
sys.modules["openlibrary.app"] = _app

_dateutil = types.ModuleType("openlibrary.utils.dateutil")
_dateutil.DAY_SECS = 86400
sys.modules["openlibrary.utils.dateutil"] = _dateutil

_cache = types.ModuleType("openlibrary.core.cache")
_cache.get_memcache = lambda: (_ for _ in ()).throw(AssertionError("stub"))
sys.modules["openlibrary.core.cache"] = _cache
_spec = importlib.util.spec_from_file_location(
    "openlibrary.views.showmarc",
    os.path.join(VIEWS_DIR, "showmarc.py"),
)
assert _spec
assert _spec.loader
_showmarc = importlib.util.module_from_spec(_spec)
sys.modules["openlibrary.views.showmarc"] = _showmarc
_spec.loader.exec_module(_showmarc)


class FakeMemcache:
    """Mimics MemcacheCache: JSON-safe values, like-for-like API."""

    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, expires=0):
        json.dumps(value)  # must stay JSON-safe (bytes go base64)
        self.store[key] = value


@pytest.fixture
def showmarc(monkeypatch):
    fake = FakeMemcache()
    monkeypatch.setattr(_cache, "get_memcache", lambda: fake)
    monkeypatch.setattr(_showmarc.requests, "get", MagicMock())
    fake.store.clear()
    return _showmarc, fake


RECORD = b"00010nam a2200005 a 4500" + b"x" * 500


def _response(content=RECORD):
    resp = MagicMock()
    resp.content = content
    resp.raise_for_status = lambda: None
    return resp


def test_cache_key_format(showmarc):
    module, _ = showmarc
    assert module._marc_cache_key("f.mrc", 10, 20) == "marc:f.mrc:10:20"


def test_miss_fetches_and_stores_json_safe(showmarc):
    module, fake = showmarc
    module.requests.get.return_value = _response()
    out = module._cached_marc_record("f.mrc", 0, 100)
    assert out == RECORD
    assert module.requests.get.call_count == 1
    assert len(fake.store) == 1


def test_hit_does_not_fetch(showmarc):
    module, fake = showmarc
    fake.store[module._marc_cache_key("f.mrc", 0, 100)] = b64encode(RECORD).decode("ascii")
    out = module._cached_marc_record("f.mrc", 0, 100)
    assert out == RECORD
    assert module.requests.get.call_count == 0


def test_timeout_with_empty_cache_raises(showmarc):
    module, _ = showmarc
    module.requests.get.side_effect = requests.Timeout()
    with pytest.raises(requests.Timeout):
        module._cached_marc_record("f.mrc", 0, 100)


def test_broken_cache_falls_back_to_live(showmarc):
    module, fake = showmarc
    fake.get = MagicMock(side_effect=Exception("down"))
    module.requests.get.return_value = _response()
    assert module._cached_marc_record("f.mrc", 0, 100) == RECORD


def test_poisoned_cache_entry_counts_as_miss(showmarc):
    module, fake = showmarc
    fake.store[module._marc_cache_key("f.mrc", 0, 100)] = "!!!not-base64!!!"
    module.requests.get.return_value = _response()
    assert module._cached_marc_record("f.mrc", 0, 100) == RECORD
    assert module.requests.get.call_count == 1
