"""pytest configuration for openlibrary"""

import pytest
import web

from infogami.infobase.tests.pytest_wildcard import Wildcard
from infogami.utils import template
from infogami.utils.view import render_template as infobase_render_template
from openlibrary.core import helpers
from openlibrary.i18n import gettext
from openlibrary.mocks.mock_ia import mock_ia  # noqa: F401 side effects may be needed
from openlibrary.mocks.mock_infobase import (
    mock_site,  # noqa: F401 side effects may be needed
)
from openlibrary.mocks.mock_memcache import (
    mock_memcache,  # noqa: F401 side effects may be needed
)


@pytest.fixture(autouse=True)
def no_requests(monkeypatch):
    def mock_request(*args, **kwargs):
        raise Warning('Network requests are blocked in the testing environment')

    monkeypatch.setattr("requests.sessions.Session.request", mock_request)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    def mock_sleep(*args, **kwargs):
        raise Warning('''
            Sleeping is blocked in the testing environment.
            Use monkeytime instead; it stubs time.time() and time.sleep().

            Eg:
                def test_foo(monkeytime):
                    assert time.time() == 1
                    time.sleep(1)
                    assert time.time() == 2

            If you need more methods stubbed, edit monkeytime in openlibrary/conftest.py
            ''')

    monkeypatch.setattr("time.sleep", mock_sleep)


@pytest.fixture(autouse=True)
def setup_db_config():
    """
    Set up empty database configuration for all tests to prevent db_parameters errors.

    This fixture is required for tests that use `create_site()` calls (anything that tests fastapi endpoints),
    especially when setting up context variables. It ensures that the database configuration is stubbed out,
    which is necessary for the context variable infrastructure being added. Without this, tests may fail due to
    missing or incorrect database parameters when initializing site.
    """
    import web

    from infogami import config

    # Set web.config.db_parameters for OLConnection
    web.config.db_parameters = {}

    # Set infobase_parameters to use local connection instead of OLConnection
    # This prevents the database configuration error when tests run
    config.infobase_parameters = {'type': 'local'}


@pytest.fixture
def monkeytime(monkeypatch):
    cur_time = 1

    def time():
        return cur_time

    def sleep(secs):
        nonlocal cur_time
        cur_time += secs

    monkeypatch.setattr("time.time", time)
    monkeypatch.setattr("time.sleep", sleep)


@pytest.fixture
def request_context_fixture():
    """
    Set up RequestContextVars for tests that need context variables.

    Provides defaults and allows tests to override any subset of fields.
    Automatically cleans up after the test.
    """
    from openlibrary.utils.request_context import RequestContextVars, req_context

    tokens = []

    def set_context(**overrides):
        current = req_context.get(
            RequestContextVars(
                x_forwarded_for=None,
                user_agent=None,
                lang=None,
                solr_editions=True,
                print_disabled=False,
                is_bot=False,
                sfw=False,
            )
        )

        new = RequestContextVars(
            x_forwarded_for=overrides.get("x_forwarded_for", current.x_forwarded_for),
            user_agent=overrides.get("user_agent", current.user_agent),
            lang=overrides.get("lang", current.lang),
            solr_editions=overrides.get("solr_editions", current.solr_editions),
            print_disabled=overrides.get("print_disabled", current.print_disabled),
            is_bot=overrides.get("is_bot", current.is_bot),
            sfw=overrides.get("sfw", current.sfw),
        )

        token = req_context.set(new)
        tokens.append(token)
        return token

    set_context()

    yield set_context

    for token in tokens:
        req_context.reset(token)


@pytest.fixture
def wildcard():
    return Wildcard()


@pytest.fixture
def render_template(request):
    """Utility to test templates."""
    template.load_templates("openlibrary")

    # TODO: call setup on upstream and openlibrary plugins to
    # load all globals.
    web.template.Template.globals["_"] = gettext
    web.template.Template.globals.update(helpers.helpers)

    web.ctx.env = web.storage()
    web.ctx.headers = []
    web.ctx.lang = "en"

    # ol_infobase.init_plugin call is failing when trying to import plugins.openlibrary.code.
    # monkeypatch to avoid that.
    from openlibrary.plugins import ol_infobase

    init_plugin = ol_infobase.init_plugin
    ol_infobase.init_plugin = lambda: None

    from openlibrary.plugins.openlibrary import code

    web.config.db_parameters = {}
    code.setup_template_globals()

    def render(name, *a, **kw):
        as_string = kw.pop("as_string", True)
        d = infobase_render_template(name, *a, **kw)
        return str(d) if as_string else d

    yield render

    ol_infobase.init_plugin = init_plugin
    template.disktemplates.clear()
    web.ctx.clear()
