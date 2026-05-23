"""Tests for the Phase 3 Jinja2 template experiment.

Validates that the Jinja2 AffiliateLinks template renders correctly
and produces semantically equivalent HTML to the Templetor template.

Uses Jinja2 directly (not via partials.py) to avoid web.py dependency
which is unavailable on Python 3.14+.
"""

from dataclasses import dataclass
from pathlib import Path

import pytest

JINJA2_AVAILABLE = False
try:
    import jinja2  # noqa: F401
except ImportError:
    pass
else:
    JINJA2_AVAILABLE = True

pytestmark = pytest.mark.skipif(
    not JINJA2_AVAILABLE, reason="Jinja2 is not installed"
)

WEBPY_AVAILABLE = False
WEBPY_GETTEXT = None
try:
    import web

    WEBPY_AVAILABLE = True
except ImportError:
    pass

if WEBPY_AVAILABLE:

    def _gettext_stub(message, *args, **kwargs):
        if kwargs:
            return message % kwargs
        return message

    WEBPY_GETTEXT = _gettext_stub


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
MACROS_DIR = PROJECT_ROOT / "macros"


def _make_jinja_env():
    """Create a Jinja2 environment configured like the production experiment."""
    from jinja2 import Environment, FileSystemLoader

    env = Environment(
        loader=FileSystemLoader(str(MACROS_DIR)),
        autoescape=True,
    )

    def fake_gettext(message: str, **kwargs) -> str:
        if kwargs:
            return message % kwargs
        return message

    env.globals["_"] = fake_gettext
    return env


def _normalize_html(html: str) -> str:
    """Collapse all non-semantic whitespace in HTML for comparison between engines."""
    import re

    html = re.sub(r">\s+<", "><", html)
    html = re.sub(r"\s{2,}", " ", html)
    return html.strip()


@pytest.fixture(scope="module")
def jinja_env():
    return _make_jinja_env()


@pytest.fixture(scope="module")
def affiliate_links_template(jinja_env):
    return jinja_env.get_template("AffiliateLinks.html.jinja")


# --- Test data objects ---


@dataclass
class _AffiliateStore:
    key: str
    analytics_key: str
    name: str
    link: str
    price: str | None = None
    price_note: str = ""


# --- _normalize_html tests ---


class TestNormalizeHtml:
    def test_collapses_whitespace_between_tags(self):
        assert _normalize_html("<div>  <span>a</span>  </div>") == "<div><span>a</span></div>"

    def test_preserves_inner_text_whitespace(self):
        assert _normalize_html("<span>hello world</span>") == "<span>hello world</span>"

    def test_empty_string(self):
        assert _normalize_html("") == ""

    def test_strips_outer_whitespace(self):
        assert _normalize_html("  <div>text</div>  ") == "<div>text</div>"


# --- Jinja2 rendering tests ---


class TestJinja2TemplateRendering:
    """Tests that the Jinja2 template renders without errors and produces expected output."""

    def test_renders_empty_stores(self, affiliate_links_template):
        result = affiliate_links_template.render(primary_stores=[], more_stores=[])
        assert '<span class="affiliate-links-section">' in result
        assert '<ul class="buy-options-table">' in result

    def test_contains_small_commission_text(self, affiliate_links_template):
        result = affiliate_links_template.render(primary_stores=[], more_stores=[])
        assert "small commission" in result
        assert "help/faq/about" in result

    def test_renders_single_primary_store(self, affiliate_links_template):
        stores = [
            _AffiliateStore(
                key="amazon",
                analytics_key="Amazon",
                name="Amazon",
                link="https://amazon.com/dp/123",
                price="$10.00",
                price_note="",
            ),
        ]
        result = affiliate_links_template.render(primary_stores=stores, more_stores=[])
        assert "prices-amazon" in result
        assert "Amazon" in result
        assert "$10.00" in result

    def test_renders_store_without_price(self, affiliate_links_template):
        stores = [
            _AffiliateStore(
                key="bookshop-org",
                analytics_key="BookshopOrg",
                name="Bookshop.org",
                link="https://bookshop.org/a/test/123",
            ),
        ]
        result = affiliate_links_template.render(primary_stores=stores, more_stores=[])
        assert "Bookshop.org" in result
        assert "price" not in result or result.count('<span name="price">') == 0

    def test_renders_more_stores_section(self, affiliate_links_template):
        stores = [
            _AffiliateStore(key="amazon", analytics_key="Amazon", name="Amazon", link="https://amazon.com/dp/123"),
        ]
        more = [
            _AffiliateStore(
                key="bookshop-org",
                analytics_key="BookshopOrg",
                name="Bookshop.org",
                link="https://bookshop.org/a/test/123",
            ),
        ]
        result = affiliate_links_template.render(primary_stores=stores, more_stores=more)
        assert "<summary>" in result
        assert "Bookshop.org" in result

    def test_no_more_stores_section_when_empty(self, affiliate_links_template):
        stores = [
            _AffiliateStore(key="amazon", analytics_key="Amazon", name="Amazon", link="https://amazon.com/dp/123"),
        ]
        result = affiliate_links_template.render(primary_stores=stores, more_stores=[])
        assert "<summary>" not in result

    def test_special_characters_escaped(self, affiliate_links_template):
        stores = [
            _AffiliateStore(
                key="amazon",
                analytics_key="Amazon",
                name="Amazon & Co.",
                link="https://amazon.com/dp/123?tag=a&b=c",
                price="$10 & up",
                price_note=" + tax",
            ),
        ]
        result = affiliate_links_template.render(primary_stores=stores, more_stores=[])
        assert 'href="https://amazon.com/dp/123?tag=a&amp;b=c"' in result
        assert "Amazon &amp; Co." in result
        assert "$10 &amp; up" in result

    def test_all_fields_present_in_output(self, affiliate_links_template):
        stores = [
            _AffiliateStore(
                key="test-key",
                analytics_key="TestAnalytics",
                name="Test Store",
                link="https://example.com/book",
                price="$19.99",
                price_note=" - note",
            ),
        ]
        result = affiliate_links_template.render(primary_stores=stores, more_stores=[])
        assert "prices-test-key" in result
        assert "TestAnalytics" in result
        assert "Test Store" in result
        assert "https://example.com/book" in result
        assert "$19.99" in result
        assert " - note" in result

    def test_output_analytics_tracking_attr(self, affiliate_links_template):
        stores = [
            _AffiliateStore(
                key="amazon",
                analytics_key="Amazon",
                name="Amazon",
                link="https://amazon.com/dp/123",
            ),
        ]
        result = affiliate_links_template.render(primary_stores=stores, more_stores=[])
        assert 'data-ol-link-track="BuyLink|Amazon"' in result


# --- Equivalence tests (need web.py for Templetor) ---


@pytest.mark.skipif(not WEBPY_AVAILABLE or WEBPY_GETTEXT is None, reason="web.py or gettext not available")
class TestTempletorEquivalence:
    """Compares Jinja2 output against Templetor output for the same inputs.

    Requires web.py (web-py) to be installed, which is only available
    on Python 3.12 or earlier.
    """

    @pytest.fixture(scope="class")
    def templetor_template(self):
        web.template.Template.globals["_"] = WEBPY_GETTEXT
        source = (MACROS_DIR / "AffiliateLinks.html").read_text()
        return web.template.Template(source)

    def _render_both(self, templetor_template, affiliate_links_template, stores, more):
        templetor_html = str(templetor_template(stores, more))
        jinja2_html = affiliate_links_template.render(primary_stores=stores, more_stores=more)
        return templetor_html, jinja2_html

    def test_empty_stores_match(self, templetor_template, affiliate_links_template):
        t, j = self._render_both(templetor_template, affiliate_links_template, [], [])
        assert _normalize_html(t) == _normalize_html(j)

    def test_primary_stores_only_match(self, templetor_template, affiliate_links_template):
        stores = [
            _AffiliateStore(
                key="betterworldbooks",
                analytics_key="BetterWorldBooks",
                name="Better World Books",
                link="https://www.betterworldbooks.com/product/detail/123",
                price="$9.99",
                price_note=" - includes shipping",
            ),
            _AffiliateStore(
                key="amazon",
                analytics_key="Amazon",
                name="Amazon",
                link="https://www.amazon.com/dp/123/?tag=test",
                price="$14.99",
                price_note="",
            ),
        ]
        t, j = self._render_both(templetor_template, affiliate_links_template, stores, [])
        assert _normalize_html(t) == _normalize_html(j)

    def test_primary_and_more_stores_match(self, templetor_template, affiliate_links_template):
        stores = [
            _AffiliateStore(key="amazon", analytics_key="Amazon", name="Amazon", link="https://amazon.com/dp/123"),
        ]
        more = [
            _AffiliateStore(
                key="bookshop-org",
                analytics_key="BookshopOrg",
                name="Bookshop.org",
                link="https://bookshop.org/a/test/123",
            ),
        ]
        t, j = self._render_both(templetor_template, affiliate_links_template, stores, more)
        assert _normalize_html(t) == _normalize_html(j)

    def test_multiple_stores_detailed_match(self, templetor_template, affiliate_links_template):
        stores = [
            _AffiliateStore(
                key="betterworldbooks",
                analytics_key="BetterWorldBooks",
                name="Better World Books",
                link="https://www.betterworldbooks.com/product/detail/9781234567890",
                price="$4.99",
                price_note=" - includes shipping",
            ),
            _AffiliateStore(
                key="amazon",
                analytics_key="Amazon",
                name="Amazon.com",
                link="https://www.amazon.com/dp/9781234567890/?tag=ol-20",
                price="$12.50",
                price_note="",
            ),
        ]
        more = [
            _AffiliateStore(
                key="bookshop-org",
                analytics_key="BookshopOrg",
                name="Bookshop.org",
                link="https://bookshop.org/a/1234/9781234567890",
            ),
        ]
        t, j = self._render_both(templetor_template, affiliate_links_template, stores, more)
        assert _normalize_html(t) == _normalize_html(j)
