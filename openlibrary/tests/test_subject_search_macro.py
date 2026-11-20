"""`macros/SubjectSearch.html.jinja`, the subject search form embedded in wiki pages.

The Templetor macro `SubjectSearch.html` is now a wrapper that reads `?q=` and
passes it in, so the form itself can be rendered from FastAPI without a request
read inside the template (docs/core/fastapi-pages.md).

These pin the two things the port must not change: the markup the form renders,
and that the value lands inside the `value="…"` attribute rather than escaping
it.
"""

import pytest
from bs4 import BeautifulSoup

from openlibrary.core.jinja import get_jinja_env, render_jinja_template

# A quote closes `value="`, after which a bare word becomes a new attribute.
INJECTION_PAYLOAD = '" onfocus=alert(document.cookie) x="'


def _form(q: str = "") -> BeautifulSoup:
    html = render_jinja_template("SubjectSearch.html.jinja", q=q)
    return BeautifulSoup(html, "lxml").find("form")


def test_renders_the_search_form(request_context_fixture):
    request_context_fixture(lang="en")

    form = _form()

    assert form["action"] == "/search/subjects"
    assert form["class"] == ["olform"]
    assert form.find("input", {"name": "q"})["id"] == "searchSubjects"
    assert form.find("label", {"for": "searchSubjects"}) is not None
    assert form.find("input", {"type": "submit"}) is not None


def test_the_query_is_prefilled(request_context_fixture):
    request_context_fixture(lang="en")

    assert _form("dinosaurs").find("input", {"name": "q"})["value"] == "dinosaurs"


def test_no_query_leaves_the_field_empty(request_context_fixture):
    request_context_fixture(lang="en")

    assert _form().find("input", {"name": "q"})["value"] == ""


def test_the_query_cannot_break_out_of_the_value_attribute(request_context_fixture):
    """`?q=` comes from any visitor, so it is the untrusted value here."""
    request_context_fixture(lang="en")

    field = _form(INJECTION_PAYLOAD).find("input", {"name": "q"})

    assert field.get("onfocus") is None
    assert field["value"] == INJECTION_PAYLOAD


def test_the_macro_can_be_called_directly(request_context_fixture):
    """FastAPI will import the macro rather than render the file."""
    request_context_fixture(lang="en")

    template = get_jinja_env().get_template("SubjectSearch.html.jinja")
    html = template.module.subject_search("dinosaurs")

    assert BeautifulSoup(html, "lxml").find("input", {"name": "q"})["value"] == "dinosaurs"


@pytest.mark.parametrize("q", ["", "dinosaurs", INJECTION_PAYLOAD])
def test_rendering_the_file_matches_calling_the_macro(request_context_fixture, q):
    """The file-level call and the importable macro must not drift apart."""
    request_context_fixture(lang="en")

    template = get_jinja_env().get_template("SubjectSearch.html.jinja")

    assert render_jinja_template("SubjectSearch.html.jinja", q=q).strip() == template.module.subject_search(q).strip()
