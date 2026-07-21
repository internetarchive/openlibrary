"""Regression tests for issue #13186 (follow-up to PR #12985's Follow.html fix).

Templetor's bare `$var` substitution HTML-escapes `<`, `>`, `&`, `"` but not
whitespace. Before this fix, onboarding_card.html, header_dropdown.html,
modal_links.html, and title_and_author.html each built the tracking attribute
as a single pre-formatted "attr=value" string spliced into the tag unquoted --
so a value containing a space (e.g. "x onmouseover=alert(1)//") injects a real
new HTML attribute, because the escaped `"` characters become inert `&quot;`
text rather than real quote delimiters. The fix places the value inside a
*static*, template-source quote character instead, which can't be broken out
of regardless of what the value contains.
"""

from bs4 import BeautifulSoup

INJECTION_PAYLOAD = "x onmouseover=alert(document.cookie)//"


def test_onboarding_card_blocks_attribute_injection(render_template, request_context_fixture):
    request_context_fixture(lang="en")
    html = str(
        render_template(
            "home/onboarding_card",
            "Title",
            "Body",
            "/img.png",
            "/href",
            ol_link_track=INJECTION_PAYLOAD,
        )
    )
    a = BeautifulSoup(html, "lxml").find("a")
    assert a.get("onmouseover") is None
    assert a["data-ol-link-track"] == INJECTION_PAYLOAD


def test_header_dropdown_singleton_blocks_attribute_injection(render_template, request_context_fixture):
    request_context_fixture(lang="en")
    props = {"name": "test-dropdown", "label": "Test", "links": [{"href": "/x", "track": INJECTION_PAYLOAD}]}
    html = str(render_template("lib/header_dropdown", props, track_prefix="Test"))
    a = BeautifulSoup(html, "lxml").find("a")
    assert a.get("onmouseover") is None
    assert a["data-ol-link-track"] == f"Test|{INJECTION_PAYLOAD}"


def test_header_dropdown_menu_item_blocks_attribute_injection(render_template, request_context_fixture):
    request_context_fixture(lang="en")
    props = {
        "name": "test-dropdown",
        "label": "Test",
        "links": [
            {"href": "/x", "track": INJECTION_PAYLOAD, "text": "Item one"},
            {"href": "/y", "track": INJECTION_PAYLOAD, "text": "Item two"},
        ],
    }
    html = str(render_template("lib/header_dropdown", props, track_prefix="Test"))
    links = BeautifulSoup(html, "lxml").find_all("a", href=True)
    menu_links = [a for a in links if a["href"] in ("/x", "/y")]
    assert len(menu_links) == 2
    for a in menu_links:
        assert a.get("onmouseover") is None
        assert a["data-ol-link-track"] == f"Test|{INJECTION_PAYLOAD}"


def test_icon_link_pattern_blocks_attribute_injection(render_template, request_context_fixture):
    """Covers the icon_link() pattern duplicated in modal_links.html and
    title_and_author.html -- see openlibrary/templates/tests/icon_link_pattern_check.html."""
    request_context_fixture(lang="en")
    html = str(render_template("tests/icon_link_pattern_check", ga_data=INJECTION_PAYLOAD))
    a = BeautifulSoup(html, "lxml").find("a")
    assert a.get("onmouseover") is None
    assert a["data-ol-link-track"] == INJECTION_PAYLOAD
