"""Keeps tests from leaking process-wide state (ContextVars, global config) into later tests.

Without this, a test's result can depend on which tests ran before it in the same process,
and pytest-xdist changes that from run to run.
"""

import contextlib
import contextvars
import os
import sys

# Tests must behave the same in the dev container as in CI, so drop the
# deployment flags compose sets before anything reads them (some modules do at
# import time). A test that needs dev-mode behaviour uses the local_dev fixture.
os.environ.pop("LOCAL_DEV", None)
os.environ.pop("OL_DEPLOYMENT_NAME", None)

import pytest
import web

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


@contextlib.contextmanager
def _restoring_global_config():
    """On exit, put back the top-level names in these namespaces and remove any added since.

    infogami and web.py keep their config in module globals, and code such as get_solr_base_url()
    loads conf/openlibrary.yml into them the first time it runs. Values changed in place aren't restored.
    """
    namespaces = [
        vars(infogami_config),
        vars(infobase_config),
        web.config,
        vars(web),  # scripts keep clients built from the config on it, e.g. web.amazon_api
        vars(openlibrary_config),
        vars(coverstore_config),
        vars(solr_utils),  # caches the Solr URL from the config
        vars(cache.memcache_cache),  # caches a memcache client built from the config
        vars(stats),  # holds a statsd client built from the config
    ]
    saved = [dict(namespace) for namespace in namespaces]
    saved_path = list(sys.path)  # infogami.load_config() appends the config's python_path
    yield
    for namespace, before in zip(namespaces, saved):
        for key in namespace.keys() - before.keys():
            del namespace[key]
        namespace.update(before)
    sys.path[:] = saved_path


# One fixture per scope, so a setup_module() or a module-scoped fixture can't leak config past its module or class.
@pytest.fixture(autouse=True, scope="module")
def restore_global_config_after_module():
    with _restoring_global_config():
        yield


@pytest.fixture(autouse=True, scope="class")
def restore_global_config_after_class():
    with _restoring_global_config():
        yield


# Autouse in the root conftest, so it's set up before the fixtures a test requests and its snapshot comes before their changes.
@pytest.fixture(autouse=True)
def restore_global_config():
    with _restoring_global_config():
        yield
