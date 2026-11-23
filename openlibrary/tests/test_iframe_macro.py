import pytest
from bs4 import BeautifulSoup

from openlibrary.core.jinja import get_jinja_env, render_jinja_template

ALLOWED = [
    "https://www.archive.org/details/x",
    "https://archive.org/details/x",
    "http://www.archive.org/details/x",
    "http://archive.org/details/x",
    "//archive.org/details/x",
]

QUOTE_PAYLOAD = '" onload=alert(document.cookie) x="'


def _render(url: str, attrs: dict | None = None) -> str:
    """Render the way the Templetor `iframe` macro does."""
    return render_jinja_template("iframe.html.jinja", url=url, attrs=attrs or {})


def _frame(url: str, attrs: dict | None = None):
    return BeautifulSoup(_render(url, attrs), "lxml").find("iframe")


@pytest.mark.parametrize("url", ALLOWED)
def test_allowed_hosts_render_an_iframe(url):
    assert _frame(url)["src"] == url


@pytest.mark.parametrize(
    "url",
    [
        "https://archive.org.evil.example/x",
        "http://evil.example/details/x",
        "//evil.example/x",
        "javascript:alert(1)",
        "",
    ],
)
def test_other_urls_render_nothing(url):
    assert _frame(url) is None


def test_attributes_are_rendered():
    frame = _frame(ALLOWED[0], {"width": "640", "height": "480"})

    assert frame["width"] == "640"
    assert frame["height"] == "480"


def test_a_quote_in_a_value_cannot_open_a_new_attribute():
    frame = _frame(ALLOWED[0], {"title": QUOTE_PAYLOAD})

    assert frame.get("onload") is None
    assert frame["title"] == QUOTE_PAYLOAD


def test_an_attribute_name_cannot_smuggle_markup():
    with pytest.raises(ValueError, match="Invalid character in attribute name"):
        _render(ALLOWED[0], {'x onload="alert(1)"': "1"})


def test_the_imported_macro_matches_the_rendered_file():
    attrs = {"width": "640", "title": QUOTE_PAYLOAD}
    macro = get_jinja_env().get_template("iframe.html.jinja").module.iframe

    assert macro(ALLOWED[0], attrs).strip() == _render(ALLOWED[0], attrs).strip()
