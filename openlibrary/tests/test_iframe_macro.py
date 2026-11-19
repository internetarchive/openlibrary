"""`macros/iframe.html.jinja`, the archive.org embed written into wiki page bodies.

The Templetor version built its extra attributes by hand:

    $:' '.join('%s="%s"' % (k, v) for k, v in attrs.items())

and spliced the result in unescaped. A value containing a double quote therefore
closed the attribute and whatever followed became real markup: on master,
``title='x" onload="alert(1)'`` renders a live ``onload`` handler and truncates
the title to ``x``.

These pin the fix (Jinja's ``xmlattr``) and the allowlist, which this port
deliberately leaves as it found it.
"""

import pytest
from bs4 import BeautifulSoup

from openlibrary.core.jinja import get_jinja_env, render_jinja_template

ALLOWED = [
    "http://www.archive.org/details/x",
    "http://archive.org/details/x",
    "//archive.org/details/x",
]

# Closes `="`, then a bare word would become a new attribute.
QUOTE_PAYLOAD = '" onload=alert(document.cookie) x="'
# The classic unquoted-attribute payload. It does not break out on master --
# the join does wrap each value in quotes -- so this is a guard against a
# future change that stops quoting, not a reproduction of the old bug.
SPACE_PAYLOAD = "x onload=alert(document.cookie)"


def _render(url: str, attrs: dict | None = None) -> str:
    template = get_jinja_env().get_template("iframe.html.jinja")
    return template.module.iframe(url, attrs or {})


def _frame(url: str, attrs: dict | None = None):
    return BeautifulSoup(_render(url, attrs), "lxml").find("iframe")


@pytest.mark.parametrize("url", ALLOWED)
def test_allowed_hosts_render_an_iframe(url):
    assert _frame(url)["src"] == url


@pytest.mark.parametrize(
    "url",
    [
        # Unchanged from master: https is NOT in the allowlist. Left as found,
        # per the scope note on #14387 -- it is behaviour, not escaping.
        "https://archive.org/details/x",
        "https://www.archive.org/details/x",
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


def test_a_space_in_a_value_cannot_open_a_new_attribute():
    frame = _frame(ALLOWED[0], {"title": SPACE_PAYLOAD})

    assert frame.get("onload") is None
    assert frame["title"] == SPACE_PAYLOAD


def test_an_attribute_name_cannot_smuggle_markup():
    """Jinja >= 3.1.5 rejects keys with whitespace, `/`, `>` or `=`."""
    with pytest.raises(ValueError, match="Invalid character in attribute name"):
        _render(ALLOWED[0], {'x onload="alert(1)"': "1"})


# The Templetor wrapper does not import the macro -- it renders the file through
# render_jinja_template, which goes through the `{% if url is defined %}` guard
# and the `attrs | default({})` wiring at the bottom. Exercise that path too, or
# a typo in those kwargs passes every test above.


def _frame_via_wrapper(**kwargs):
    html = render_jinja_template("iframe.html.jinja", **kwargs)
    return BeautifulSoup(html, "lxml").find("iframe")


def test_the_wrapper_entry_point_renders_an_iframe():
    frame = _frame_via_wrapper(url=ALLOWED[0], attrs={"width": "640"})

    assert frame["src"] == ALLOWED[0]
    assert frame["width"] == "640"


def test_the_wrapper_entry_point_applies_the_allowlist():
    assert _frame_via_wrapper(url="https://archive.org/details/x", attrs={}) is None


def test_the_wrapper_entry_point_defaults_attrs():
    """`attrs | default({})` -- rendering with only a url must not raise."""
    assert _frame_via_wrapper(url=ALLOWED[0])["src"] == ALLOWED[0]


def test_rendering_the_file_matches_calling_the_macro():
    """The file-level call and the importable macro must not drift apart."""
    attrs = {"width": "640", "title": QUOTE_PAYLOAD}

    assert render_jinja_template("iframe.html.jinja", url=ALLOWED[0], attrs=attrs).strip() == _render(ALLOWED[0], attrs).strip()
