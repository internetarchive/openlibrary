from urllib.parse import parse_qs, urlencode, urlparse
import web

from infogami.utils.view import public

from openlibrary.i18n import gettext as _


@public
def get_quality_criteria():
    def build_url(query_fragment, for_ui=True):
        page_path = web.ctx.path
        on_author_page = page_path.startswith('/authors/OL')
        base_query = f"?q=author_key:{page_path.split('/')[2]}" if on_author_page else web.ctx.query

        parsed_query = urlparse(base_query)
        params = parse_qs(parsed_query.query)
        q = params.get("q", [""])[0]
        q += f" {query_fragment}"
        params["q"] = [q]

        if for_ui:
            return f"/search?{urlencode(params, doseq=True)}"

        params["rows"] = ["0"]
        return f"/search.json?{urlencode(params, doseq=True)}"

    return [
        {
            "name": _("At least 1 subject"),
            "queryFragment": "NOT subject:*",
        },
        {
            "name": _("At least 1 author"),
            "queryFragment": "NOT author_key:*",
        },
        {
            "name": _("At least 1 edition"),
            "queryFragment": "edition_count:0",
        },
        {
            "name": _("Has work (orphaned)"),
            "queryFragment": "key:*M",
        },
        {
            "name": _("Has publication year"),
            "queryFragment": "NOT publish_year:*",
        },
        {
            "name": _("Has cover"),
            "queryFragment": "NOT cover_i:*",
        },
        {
            "name": _("Has language"),
            "queryFragment": "NOT language:*",
        },
        {
            "name": _("Has publisher"),
            "queryFragment": "NOT publisher:*",
        },
        {
            "name": _("At least 2 editions"),
            "queryFragment": "edition_count:[0 TO 1]",
        },
        {
            "name": _("Has dewey decimal"),
            "queryFragment": "NOT ddc:*",
        },
        {
            "name": _("Has LoC classification"),
            "queryFragment": "NOT lcc:*",
        },
        {
            "name": _("Has number of pages"),
            "queryFragment": "NOT number_of_pages_median:*",
        },
    ]
