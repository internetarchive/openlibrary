"""`/search/bulk` HTML page on FastAPI.

It renders `bulk_search/bulk_search.html.jinja`; the web.py handler still renders
the same template until ops routes /search/bulk to FastAPI in production. The
shell around the page is tested in `test_site_page.py`; these test the page's
own body.
"""

import json
import pathlib
import re
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from openlibrary.fastapi.search import pages

I18N_ATTRIBUTE = re.compile(r'\si18n="([^"]*)"')
COMPONENT_STRINGS_JS = pathlib.Path(__file__).resolve().parents[3] / "openlibrary/components/BulkSearch/utils/i18n.js"


@pytest.fixture
def client(site_page_app) -> TestClient:
    return TestClient(site_page_app(pages))


def i18n_strings(html: str) -> dict:
    """The translated strings the template URL-encodes onto the element."""
    match = I18N_ATTRIBUTE.search(html)
    assert match, "no i18n attribute on the component element"
    return json.loads(unquote(match.group(1)))


def component_default_keys() -> set[str]:
    """The keys of `DEFAULT_BULK_SEARCH_STRINGS` in i18n.js."""
    source = COMPONENT_STRINGS_JS.read_text()
    defaults = source.split("export const DEFAULT_BULK_SEARCH_STRINGS = {", 1)[1].split("\n};", 1)[0]
    return set(re.findall(r"^ {4}([a-zA-Z]\w*):", defaults, re.MULTILINE))


def test_bulk_search_page_renders_the_component(client):
    response = client.get("/search/bulk")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    html = response.text
    assert "<title>Bulk Search (beta) | Open Library</title>" in html
    assert "<h1>Bulk Search (beta)</h1>" in html
    assert html.count("<ol-bulk-search") == 1
    # The component's bundle, from the shell's static_url
    assert 'src="/static/build/components/production/ol-BulkSearch.js"' in html


def test_bulk_search_page_passes_the_translated_strings(client):
    response = client.get("/search/bulk")
    strings = i18n_strings(response.text)

    assert strings["extractHeading"] == "Extract Books"
    assert strings["extractorTable"] == "Extract from a Table/Spreadsheet"
    # Quotes and apostrophes survive the JSON + URL encoding
    assert strings["columnHint"].startswith('Please include a header row. Supported columns include: "Title"')
    assert strings["matchDescription"].endswith("in OpenLibrary!")
    # The browser picks the plural form, so every form keeps its placeholder
    assert set(strings["editions"]) == {"one", "two", "few", "many", "other"}
    assert all("%(count)s" in form for form in strings["editions"].values())


def test_bulk_search_page_sends_translated_text(client, monkeypatch):
    """The payload carries the request language's text, not the English msgids."""

    class Translations:
        def ugettext(self, message: str) -> str:
            return {"Extract Books": "Bücher extrahieren"}.get(message, message)

        def ungettext(self, singular: str, plural: str, n: int) -> str:
            return singular if n == 1 else plural

    monkeypatch.setattr("openlibrary.i18n.load_translations", lambda lang: Translations())

    strings = i18n_strings(client.get("/search/bulk").text)
    assert strings["extractHeading"] == "Bücher extrahieren"
    # A string with no translation keeps its English text
    assert strings["matchHeading"] == "Match Books"


def test_bulk_search_page_does_not_read_webpy_ctx(client, webpy_leftovers):
    """The page renders without web.py's request state, which a FastAPI request must not touch."""
    response = client.get("/search/bulk")

    assert response.status_code == 200
    assert webpy_leftovers not in response.text
    assert i18n_strings(response.text)["extractHeading"] == "Extract Books"


def test_bulk_search_page_ignores_query_params(client):
    response = client.get("/search/bulk?q=%3Cscript%3E&page=abc")

    assert response.status_code == 200
    assert "&lt;script&gt;" not in response.text
