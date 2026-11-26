from typing import Any

import web
from markupsafe import escape

from infogami import config  # noqa: F401 side effects may be needed
from infogami.utils import delegate
from openlibrary.core.jinja import render_jinja_template
from openlibrary.i18n import gettext as _
from openlibrary.i18n import ungettext
from openlibrary.plugins.upstream.utils import vue_component_html


def bulk_search_strings() -> dict[str, Any]:
    """Translated strings for ``<ol-bulk-search>``.

    Keys and English strings must match ``DEFAULT_STRINGS`` in
    ``openlibrary/components/BulkSearch.vue``; ``test_bulk_search_page.py`` checks
    that they do. Built in Python like ``core/shell/shelf_labels.py``, plural set included.
    """
    return {
        # NOTE: "Title", "Author" and "ISBN" are the column names the spreadsheet must use, so keep them in English.
        "columnHint": _('Please include a header row. Supported columns include: "Title", "Author", "ISBN".'),
        "enterBooks": _("Enter your books below."),
        "enterBooksHint": _("One per line, or paste from a spreadsheet."),
        "trySample": _("Try a Sample..."),
        "sample1927": _("1927 Books"),
        "samplePublicDomain2023": _("2023 Public Domain Day"),
        "sampleHolocaust": _("Holocaust Wikipedia citations"),
        "inputPlaceholder": _("Enter your books..."),
        "extractBooks": _("Extract Books"),
        "extractDescription": _("How to convert your books above into structured information, like title and author."),
        "extractor": _("Extractor"),
        "apiKey": _("OpenAI API Key"),
        "apiKeyPlaceholder": _("OpenAI API key here...."),
        "loading": _("Loading..."),
        "matchBooks": _("Match Books"),
        "matchDescription": _("Once structured data has been found, it's time to match it to a book in OpenLibrary!"),
        "options": _("Options"),
        "useAuthor": _("Use author in search query"),
        "saveMatches": _("Save your Matches"),
        "saveDescription": _("Now that you've found your books, why not save them to your reading log? Or a list?"),
        "addToList": _("Add to list"),
        # NOTE: These name the formats the extractors read. Keep the English "by" in "Title by Author": the pattern matches it.
        "patternTitleByAuthor": _("Pattern: Title by Author"),
        "patternAuthorTitle": _("Pattern: Author - Title"),
        "patternTitleAuthor": _("Pattern: Title - Author"),
        "patternTitleParenAuthor": _("Pattern: Title (Author)"),
        "patternWikipedia": _("Wikipedia Citation Pattern: (e.g. Baum, Frank L. (1994). The Wizard of Oz)"),
        "aiExtraction": _("✨ AI Extraction (Beta)"),
        "tableExtraction": _("Extract from a Table/Spreadsheet"),
        "extractedBooks": _("Extracted Books"),
        "matchedBooks": _("Matched Books"),
        "title": _("Title"),
        "author": _("Author"),
        "isbn": _("ISBN"),
        "viewResults": _("View results in Open Library"),
        "noBooksFound": _("No Books Found"),
        "editions": {
            "one": ungettext("%(count)s edition", "%(count)s editions", 1),
            "two": ungettext("%(count)s edition", "%(count)s editions", 2),
            "few": ungettext("%(count)s edition", "%(count)s editions", 3),
            "many": ungettext("%(count)s edition", "%(count)s editions", 11),
            "other": ungettext("%(count)s edition", "%(count)s editions", 100),
        },
    }


class bulk_search(delegate.page):
    path = "/search/bulk"

    def GET(self):
        body = render_jinja_template("bulk_search/bulk_search.html.jinja", vue_component_html=vue_component_html, strings=bulk_search_strings())
        # web.py's layout reads the title off the result, already escaped, as from Templetor's $var.
        return web.template.TemplateResult(__body__=body, title=escape(_("Bulk Search (beta)")))


def setup():
    pass
