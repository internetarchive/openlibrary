from bs4 import BeautifulSoup

from openlibrary.core.jinja import render_jinja_template


def _query_field(q: str):
    html = render_jinja_template("SubjectSearch.html.jinja", q=q)
    return BeautifulSoup(html, "lxml").find("form", action="/search/subjects").find("input", {"name": "q"})


def test_prefills_the_query(request_context_fixture):
    request_context_fixture(lang="en")

    assert _query_field("dinosaurs")["value"] == "dinosaurs"


def test_query_cannot_break_out_of_the_value_attribute(request_context_fixture):
    request_context_fixture(lang="en")
    payload = '" onfocus=alert(1) x="'

    field = _query_field(payload)

    assert field["value"] == payload
    assert field.get("onfocus") is None
