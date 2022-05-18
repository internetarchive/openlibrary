"""pytest configuration for openlibrary
"""
import pytest
import web

from infogami.infobase.tests.pytest_wildcard import Wildcard
from infogami.utils import template
from infogami.utils.view import render_template as infobase_render_template
from openlibrary.i18n import gettext
from openlibrary.core import helpers

from openlibrary.mocks.mock_infobase import mock_site  # noqa: F401
from openlibrary.mocks.mock_ia import mock_ia  # noqa: F401
from openlibrary.mocks.mock_memcache import mock_memcache  # noqa: F401


@pytest.fixture(autouse=True)
def no_requests(monkeypatch):
    def mock_request(*args, **kwargs):
        raise Warning('Network requests are blocked in the testing environment')

    monkeypatch.setattr("requests.sessions.Session.request", mock_request)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    def mock_sleep(*args, **kwargs):
        raise Warning(
            '''
            Sleeping is blocked in the testing environment.
            Use monkeytime instead; it stubs time.time() and time.sleep().

            Eg:
                def test_foo(monkeytime):
                    assert time.time() == 1
                    time.sleep(1)
                    assert time.time() == 2

            If you need more methods stubbed, edit monkeytime in openlibrary/conftest.py
            '''
        )

    monkeypatch.setattr("time.sleep", mock_sleep)


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

    def undo():
        ol_infobase.init_plugin = init_plugin

    request.addfinalizer(undo)

    from openlibrary.plugins.openlibrary import code

    web.config.db_parameters = dict()
    code.setup_template_globals()

    def finalizer():
        template.disktemplates.clear()
        web.ctx.clear()

    request.addfinalizer(finalizer)

    def render(name, *a, **kw):
        as_string = kw.pop("as_string", True)
        d = infobase_render_template(name, *a, **kw)
        return str(d) if as_string else d

    return render
