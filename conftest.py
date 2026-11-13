"""Keeps tests from leaking process-wide state (ContextVars, global config) into later tests.

Without this, a test's result can depend on which tests ran before it in the same process,
and pytest-xdist changes that from run to run.
"""

import contextlib
import contextvars
import os
import sys
import types

# Tests must behave the same in the dev container as in CI, so drop the
# deployment flags compose sets before anything reads them (some modules do at
# import time). A test that needs dev-mode behaviour uses the local_dev fixture.
os.environ.pop("LOCAL_DEV", None)
os.environ.pop("OL_DEPLOYMENT_NAME", None)

import pytest
import web
from pymemcache.test.utils import MockMemcacheClient

from infogami import config as infogami_config
from infogami.infobase import config as infobase_config
from openlibrary import config as openlibrary_config
from openlibrary.core import cache, stats
from openlibrary.coverstore import config as coverstore_config
from openlibrary.solr import utils as solr_utils

_in_test_context = contextvars.ContextVar("_in_test_context", default=False)


@pytest.hookimpl(tryfirst=True)  # before pytest's own implementation, which would otherwise run the test
def pytest_runtest_protocol(item, nextitem):
    """Run each test and its fixtures in a throwaway copy of the contextvars context.

    App code sets the request ContextVars (site, req_context, visitor) and never resets them.
    Inside the copy this hook is called again and returns None, so pytest's own implementation
    runs the test (and hook wrappers such as pytest's warnings capture run twice, nested).

    A module-, class- or session-scoped fixture is set up inside one test's copy, so it can't
    set a ContextVar for the tests after it.
    """
    if _in_test_context.get():
        return None

    def run_test():
        _in_test_context.set(True)
        item.ihook.pytest_runtest_protocol(item=item, nextitem=nextitem)

    contextvars.copy_context().run(run_test)
    return True


@pytest.fixture(autouse=True, scope="session")
def app_plugins_imported():
    """Import the app's plugins before any test, as the web app does at startup.

    Importing them sets defaults such as infogami.config.features and web.commify. A full run imports
    them during collection anyway; this makes a run of a single test file match it.
    """
    import openlibrary.plugins.openlibrary.code  # noqa: PLC0415
    import openlibrary.plugins.upstream.code  # noqa: F401, PLC0415


@pytest.fixture(autouse=True, scope="session")
def infobase_test_config():
    """The infobase config MockSite's account manager needs, set once before any test runs."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(infogami_config, "infobase", {**(infogami_config.get("infobase") or {}), "secret_key": "foobar"}, raising=False)
        mp.setattr(infobase_config, "secret_key", "foobar", raising=False)
        mp.setattr(infobase_config, "user_root", "/people", raising=False)
        yield


@pytest.fixture(autouse=True)
def fresh_memcache(monkeypatch):
    """Give each test an empty dummy memcache client.

    The shared MemcacheCache builds its client the first time it's used and keeps it, so cached
    values would otherwise carry over from one test to the next.
    """
    monkeypatch.setitem(vars(cache.memcache_cache), "memcache", MockMemcacheClient())


def _global_config():
    """The process-wide config, and the clients built from it, that a test must leave as it found it.

    infogami and web.py keep their config in module globals, and code such as get_solr_base_url()
    loads conf/openlibrary.yml into them the first time it runs.
    """
    return {
        "infogami.config": vars(infogami_config),
        "infogami.infobase.config": vars(infobase_config),
        "web.config": web.config,
        "web": vars(web),  # scripts keep clients built from the config on it, e.g. web.amazon_api
        "openlibrary.config": vars(openlibrary_config),
        "openlibrary.coverstore.config": vars(coverstore_config),
        "openlibrary.solr.utils": vars(solr_utils),  # caches the Solr URL from the config
        "openlibrary.core.cache.memcache_cache": vars(cache.memcache_cache),  # caches a memcache client built from the config
        "openlibrary.core.stats": vars(stats),  # holds a statsd client built from the config
        "sys.path": dict.fromkeys(sys.path),  # infogami.load_config() appends the config's python_path; pytest reorders it
    }


def _snapshot():
    return {name: dict(namespace) for name, namespace in _global_config().items()}


def _changed_names(before, after):
    missing = object()
    for name, old_namespace in before.items():
        new_namespace = after[name]
        for key in old_namespace.keys() | new_namespace.keys():
            old, new = old_namespace.get(key, missing), new_namespace.get(key, missing)
            if old is new or key.startswith("__") or isinstance(new, types.ModuleType):  # importing a submodule adds it to its package
                continue
            try:
                if old == new:  # e.g. a fixture that sets the same {} before every test
                    continue
            except Exception:  # noqa: BLE001 - a value that can't be compared counts as changed
                pass
            yield f"{name}.{key}" if name != "sys.path" else f"sys.path entry {key!r}"


_reported_leaks: set[str] = set()  # so a leak reported by a test isn't reported again for its class and module


@contextlib.contextmanager
def _failing_on_config_leaks(what):
    before = _snapshot()
    yield
    changed = sorted(_changed_names(before, _snapshot()))
    if what != "test":
        changed = [name for name in changed if name not in _reported_leaks]
    _reported_leaks.update(changed)
    if changed:
        pytest.fail(
            f"This {what} changed global config and didn't undo it: {', '.join(changed)}.\n"
            "Make the change with the monkeypatch fixture (or pytest.MonkeyPatch.context() in a module- or class-scoped fixture), "
            "so it's undone afterwards. Otherwise later tests in the same process see it, and their results depend on test order.",
            pytrace=False,
        )


# Autouse in the root conftest, so it's set up before any other fixture and checks after they've all been torn down.
# Values changed in place, such as a key inside a nested dict, aren't checked.
@pytest.fixture(autouse=True)
def fail_on_config_leaks():
    with _failing_on_config_leaks("test"):
        yield


# For setup_module()/setup_class() and module- or class-scoped fixtures.
@pytest.fixture(autouse=True, scope="module")
def fail_on_config_leaks_in_module():
    with _failing_on_config_leaks("module"):
        yield


@pytest.fixture(autouse=True, scope="class")
def fail_on_config_leaks_in_class():
    with _failing_on_config_leaks("class"):
        yield
