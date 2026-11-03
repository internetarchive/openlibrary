"""Tests for the show-marc record cache (internetarchive/openlibrary#13874)."""

import json
from base64 import b64encode
from unittest.mock import MagicMock

import pytest
import requests

from openlibrary.core import cache
from openlibrary.views import showmarc as showmarc_module


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
    monkeypatch.setattr(cache, "get_memcache", lambda: fake)
    monkeypatch.setattr(showmarc_module.requests, "get", MagicMock())
    return showmarc_module, fake


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
