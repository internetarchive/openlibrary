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
            params["rows"] = ["0"]
            return f"/search?{urlencode(params, doseq=True)}"

        return f"/search.json?{urlencode(params, doseq=True)}"

    return [
        {
            "name": _("At least 1 subject"),
            "apiUrl": build_url("NOT subject:*", for_ui=False),
            "searchPageUrl": build_url("NOT subject:*"),
        },
        {
            "name": _("At least 1 author"),
            "apiUrl": build_url("NOT author_key:*", for_ui=False),
            "searchPageUrl": build_url("NOT author_key:*"),
        },
        {
            "name": _("At least 1 edition"),
            "apiUrl": build_url("edition_count:0", for_ui=False),
            "searchPageUrl": build_url("edition_count:0"),
        },
        {
            "name": _("Has work (orphaned)"),
            "apiUrl": build_url("key:*M", for_ui=False),
            "searchPageUrl": build_url("key:*M"),
        },
        {
            "name": _("Has publication year"),
            "apiUrl": build_url("NOT publish_year:*", for_ui=False),
            "searchPageUrl": build_url("NOT publish_year:*"),
        },
        {
            "name": _("Has cover"),
            "apiUrl": build_url("NOT cover_i:*", for_ui=False),
            "searchPageUrl": build_url("NOT cover_i:*"),
        },
        {
            "name": _("Has language"),
            "apiUrl": build_url("NOT language:*", for_ui=False),
            "searchPageUrl": build_url("NOT language:*"),
        },
        {
            "name": _("Has publisher"),
            "apiUrl": build_url("NOT publisher:*", for_ui=False),
            "searchPageUrl": build_url("NOT publisher:*"),
        },
        {
            "name": _("At least 2 editions"),
            "apiUrl": build_url("edition_count:[0 TO 1]", for_ui=False),
            "searchPageUrl": build_url("edition_count:[0 TO 1]"),
        },
        {
            "name": _("Has dewey decimal"),
            "apiUrl": build_url("NOT ddc:*", for_ui=False),
            "searchPageUrl": build_url("NOT ddc:*"),
        },
        {
            "name": _("Has LoC classification"),
            "apiUrl": build_url("NOT lcc:*", for_ui=False),
            "searchPageUrl": build_url("NOT lcc:*"),
        },
        {
            "name": _("Has number of pages"),
            "apiUrl": build_url("OT number_of_pages_median:*", for_ui=False),
            "searchPageUrl": build_url("OT number_of_pages_median:*"),
        },
    ]
