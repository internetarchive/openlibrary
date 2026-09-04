"""Tests for openlibrary.core.jinja — Jinja2 environment setup."""

import pathlib
import textwrap
from typing import Any

import jinja2
import jinja2.exceptions
import pytest
import web
from lxml import html as lxml_html
from lxml.etree import ParseError as LxmlParseError
from markupsafe import escape as _markupsafe_escape

from openlibrary import i18n as i18n_module
from openlibrary.core import jinja as jinja_module
from openlibrary.core.jinja import get_jinja_env
from openlibrary.i18n import load_translations
from openlibrary.utils.request_context import req_context

MACROS_DIR = pathlib.Path(__file__).resolve().parents[3] / "openlibrary" / "macros"
TEMPLATES_DIR = pathlib.Path(__file__).resolve().parents[3] / "openlibrary" / "templates"


class RenderableUndefined(jinja2.Undefined):
    """An Undefined variant that never raises during rendering.

    Renders as ``""``, is always falsy, and chains attribute/item access to
    more ``RenderableUndefined`` instances.  This lets templates render
    without mock data — ``{% if var %}`` blocks are skipped, ``{% for item
    in list %}`` loops produce no iterations, ``{{ obj.attr }}`` produces
    ``""``.

    Intended for structural HTML validation where the goal is to verify
    the hardcoded template structure, not the data paths.
    """

    __eq__ = __ne__ = __lt__ = __gt__ = __le__ = __ge__ = lambda s, o: s

    def __getattr__(self, name: str) -> RenderableUndefined:
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return RenderableUndefined()

    def __getitem__(self, key: object) -> RenderableUndefined:
        return RenderableUndefined()

    def __call__(self, *args: Any, **kwargs: Any) -> RenderableUndefined:
        return RenderableUndefined()


def _create_validation_env() -> jinja2.Environment:
    """Create a Jinja environment with ``RenderableUndefined`` for structural validation.

    Mirrors the real environment's settings (autoescape, i18n, etc.) but
    uses ``RenderableUndefined`` instead of ``StrictUndefined`` so that
    templates render without mock data.
    """

    def _gettext(message: str) -> str:

        translations = load_translations(req_context.get().lang)
        return translations.ugettext(message) if translations else message

    def _ngettext(singular: str, plural: str, n: int) -> str:

        if translations := load_translations(req_context.get().lang):
            return translations.ungettext(singular, plural, n)
        return singular if n == 1 else plural

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader([TEMPLATES_DIR, MACROS_DIR]),
        autoescape=True,
        undefined=RenderableUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        extensions=["jinja2.ext.i18n"],
    )
    env.install_gettext_callables(_gettext, _ngettext, newstyle=True)
    env.policies["ext.i18n.trimmed"] = True

    # Stubbed: this env only validates template structure, without infogami's
    # runtime template disk-loading or template globals.
    def _stub_render_templetor(*a, **kw):
        return ""

    env.globals["render_templetor_template"] = _stub_render_templetor

    env.globals["icon"] = lambda *a, **kw: ""

    # The TestingEnvironment macro renders a Vue component via
    # render_component(); this env has no component build output, so stub it
    # the same way render_templetor_template is stubbed above.
    def _stub_render_component(*a, **kw):
        return ""

    env.globals["render_component"] = _stub_render_component

    env.globals["stats_summary"] = dict
    env.globals["query_param"] = lambda name, default=None: default
    env.globals["is_bot"] = lambda: False
    env.globals["static_url"] = lambda path: f"/static/{path}"
    env.globals["get_supported_languages"] = dict
    env.globals["get_git_revision_short_hash"] = lambda: ""
    env.globals["ctx"] = RenderableUndefined()

    env.filters["force_escape"] = lambda s: _markupsafe_escape(str(s).strip())

    env.filters["dedent"] = lambda s: textwrap.dedent(str(s)).strip()

    return env


def assert_valid_html(html_string: str) -> None:
    """Assert that ``html_string`` is well-formed HTML with no orphan/mismatched tags.

    Uses lxml's HTML parser with ``recover=False``, which raises
    ``ParseError`` on unexpected closing tags (e.g., ``</span>`` without a
    matching ``<span>``).  Plain text (no HTML tags) is skipped.
    """
    if "<" not in html_string or ">" not in html_string:
        return  # plain text, nothing to validate

    parser = lxml_html.HTMLParser(recover=False)
    try:
        lxml_html.fromstring(html_string, parser=parser)
    except LxmlParseError as e:
        # libxml2's HTML parser is HTML4-based and flags HTML5 semantic elements
        # (header, footer, nav, aside, main, section, details, summary) as invalid tags.
        msg = str(e)
        if "Tag " in msg and " invalid" in msg:
            return
        pytest.fail(f"Rendered HTML contains orphan/mismatched tags: {e}")


def test_site_layout_template_uses_jinja_template(monkeypatch):
    """The ``site`` pile entry should delegate to the Jinja site wrapper."""
    rendered = "<html>"

    def mock_render(template_name, **kwargs):
        assert template_name == "site.html.jinja"
        assert kwargs == {"page": "page"}
        return rendered

    monkeypatch.setattr(jinja_module, "render_jinja_template", mock_render)

    site_template = jinja_module.SiteLayoutTemplate()
    assert site_template.filename == "openlibrary/templates/site.html.jinja"
    assert site_template("page") == rendered


class TestGetJinjaEnv:
    """Tests for get_jinja_env()."""

    def test_returns_configured_environment(self):
        """Should return a Jinja2 Environment with loaders for macros and templates."""
        env = get_jinja_env()
        assert isinstance(env, jinja2.Environment)
        assert isinstance(env.loader, jinja2.FileSystemLoader)

    def test_is_cached(self):
        """Should return the same object on repeated calls (functools.cache)."""
        env1 = get_jinja_env()
        env2 = get_jinja_env()
        assert env1 is env2

    def test_has_strict_undefined(self):
        """Should use StrictUndefined so undefined variables raise errors."""
        env = get_jinja_env()
        assert isinstance(env.undefined, type(jinja2.StrictUndefined))
        # Verify that accessing an undefined variable raises
        tpl = env.from_string("{{ nonexistent }}")

        with pytest.raises(jinja2.exceptions.UndefinedError):
            tpl.render()

    def test_has_gettext_globals(self):
        """Should have the _ (gettext) function in globals."""
        env = get_jinja_env()
        assert "_" in env.globals
        assert callable(env.globals["_"])

    def test_has_icon_global(self):
        """Should expose the icon macro as a global, since Jinja has no
        ``macros`` namespace."""
        env = get_jinja_env()
        assert "icon" in env.globals
        assert callable(env.globals["icon"])

    def test_has_render_templetor_template_global(self):
        """Should expose render_templetor_template in globals."""
        env = get_jinja_env()
        assert "render_templetor_template" in env.globals
        assert callable(env.globals["render_templetor_template"])

    def test_has_footer_helpers_in_globals(self):
        """Should expose all shared footer helpers and ctx in globals."""
        env = get_jinja_env()
        for helper in (
            "stats_summary",
            "query_param",
            "is_bot",
            "static_url",
            "get_supported_languages",
            "get_git_revision_short_hash",
        ):
            assert helper in env.globals
            assert callable(env.globals[helper])
        assert "ctx" in env.globals

    def test_footer_helpers_return_safe_defaults_when_globals_missing(self, monkeypatch):
        """Footer helpers should return safe defaults if Template globals are not populated."""
        monkeypatch.setattr(web.template.Template, "globals", {})
        env = get_jinja_env()
        assert env.globals["stats_summary"]() == {}
        assert env.globals["query_param"]("debug", "default_val") == "default_val"
        assert env.globals["is_bot"]() is False
        assert env.globals["static_url"]("build/js/all.js") == "/static/build/js/all.js"
        assert env.globals["get_supported_languages"]() == {}
        assert env.globals["get_git_revision_short_hash"]() == ""

    def test_has_autoescape_enabled(self):
        """Should have autoescaping enabled."""
        env = get_jinja_env()
        assert env.autoescape is True

    def test_has_trim_blocks_enabled(self):
        """Should have trim_blocks enabled."""
        env = get_jinja_env()
        assert env.trim_blocks is True

    def test_has_lstrip_blocks_enabled(self):
        """Should have lstrip_blocks enabled."""
        env = get_jinja_env()
        assert env.lstrip_blocks is True

    def test_can_load_and_render_affiliate_links_template(self, request_context_fixture):
        """Should be able to load the AffiliateLinks.html.jinja template
        from the macros/ directory and render it with store data."""
        request_context_fixture(lang="en")
        env = get_jinja_env()
        tpl = env.get_template("AffiliateLinks.html.jinja")
        output = tpl.render(
            primary_stores=[
                {
                    "key": "teststore",
                    "analytics_key": "TestStore",
                    "name": "Test Store",
                    "link": "https://example.com/book",
                    "price": None,  # StrictUndefined - must include all accessed attrs
                    "price_note": "",
                }
            ],
            more_stores=[],
        )
        # Should contain the store link
        assert "https://example.com/book" in output
        assert "Test Store" in output
        assert "affiliate-links-section" in output
        # Should not have HTML injection from store name
        assert "&gt;" not in output  # no encoded angle brackets from simple names

    def test_translations_via_gettext_callables(self, monkeypatch, request_context_fixture):
        """Should translate ``{% trans %}`` blocks and ``{{ gettext() }}`` / ``{{ ngettext() }}``
        calls using the per-request translations installed by
        ``install_gettext_callables``.
        """

        class MockTranslations:
            """Stand-in for Babel ``Translations`` that returns canned data."""

            def ugettext(self, message: str) -> str:
                translations = {
                    "Hello": "Bonjour",
                    "Welcome": "Bienvenue",
                }
                return translations.get(message, message)

            def ungettext(self, singular: str, plural: str, n: int) -> str:
                translations = {
                    ("book", "books"): ("livre", "livres"),
                }
                if result := translations.get((singular, plural)):
                    return result[0] if n == 1 else result[1]
                return singular if n == 1 else plural

        original_load = i18n_module.load_translations

        def mock_load(lang: str):
            if lang == "fr":
                return MockTranslations()
            return original_load(lang)

        monkeypatch.setattr(i18n_module, "load_translations", mock_load)

        env = get_jinja_env()

        # --- {% trans %} block ---
        request_context_fixture(lang="fr")
        tpl = env.from_string("{% trans %}Hello{% endtrans %}")
        assert tpl.render() == "Bonjour"

        # --- {{ _() }} uses the same installed callable (auto-registered by Jinja) ---
        tpl = env.from_string("{{ _('Hello') }}")
        assert tpl.render() == "Bonjour"

        # --- {{ gettext() }} uses the installed callable (translates only) ---
        tpl = env.from_string("{{ gettext('Hello') }}")
        assert tpl.render() == "Bonjour"

        # --- {{ ngettext() }} with singular/plural ---
        tpl = env.from_string("{{ ngettext('book', 'books', 1) }}")
        assert tpl.render() == "livre"
        tpl = env.from_string("{{ ngettext('book', 'books', 2) }}")
        assert tpl.render() == "livres"

        # --- Fallback: English when no translation exists ---
        request_context_fixture(lang="en")
        tpl = env.from_string("{% trans %}Hello{% endtrans %}")
        assert tpl.render() == "Hello"

        # --- Fallback: language with no .mo file at all ---
        request_context_fixture(lang="de")
        tpl = env.from_string("{% trans %}Hello{% endtrans %}")
        assert tpl.render() == "Hello"


def test_all_jinja_templates_render_valid_html(request_context_fixture, subtests):
    """Every ``.jinja`` template should render structurally valid HTML.

    Uses ``RenderableUndefined`` so templates render without mock data.
    Structural validation uses lxml's ``recover=False`` parser to catch
    orphan closing tags like ``</span>`` without a matching ``<span>``.
    """
    request_context_fixture(lang="en")
    env = _create_validation_env()

    macros = list(MACROS_DIR.glob("*.jinja"))
    templates = list(TEMPLATES_DIR.rglob("*.jinja"))

    assert macros or templates, f"No .jinja files found in {MACROS_DIR} or {TEMPLATES_DIR}"

    for path in sorted(macros):
        with subtests.test(template=path.name):
            tpl = env.get_template(path.name)
            output = tpl.render()
            assert_valid_html(output)

    for path in sorted(templates):
        rel = path.relative_to(TEMPLATES_DIR)
        with subtests.test(template=rel.as_posix()):
            tpl = env.get_template(rel.as_posix())
            output = tpl.render()
            assert_valid_html(output)
