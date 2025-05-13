from urllib.parse import parse_qs, urlencode, urlparse
import web

from infogami.utils.view import public

from openlibrary.i18n import gettext as _


@public
def get_quality_criteria():
    def build_work_search_url(query_fragment):
        page_path = web.ctx.path
        on_author_page = page_path.startswith('/authors/OL')
        if on_author_page:
            base_query = f"?q=author_key:{page_path.split('/')[2]}"
        else:
            base_query = f"{web.ctx.query}"

        parsed_query = urlparse(base_query)
        params = parse_qs(parsed_query.query)
        q = params.get("q", [""])[0]
        q += f" {query_fragment}"
        params["q"] = [q]

        return f"/search.json?{urlencode(params, doseq=True)}"


    def build_search_page_url(query_fragment):
        page_path = web.ctx.path
        on_author_page = page_path.startswith('/authors/OL')
        if on_author_page:
            base_query = f"?q=author_key:{page_path.split('/')[2]}"
        else:
            base_query = f"{web.ctx.query}"

        parsed_query = urlparse(base_query)
        params = parse_qs(parsed_query.query)
        q = params.get("q", [""])[0]
        q += f" {query_fragment}"
        params["q"] = [q]
        params["rows"] = ["0"]

        return f"/search?{urlencode(params, doseq=True)}"

    return [
        {
            "name": _("At least 1 subject"),
            "apiUrl": build_work_search_url("NOT subject:*"),
            "searchPageUrl": build_search_page_url("NOT subject:*"),
        },
        {
            "name": _("At least 1 author"),
            "apiUrl": build_work_search_url("NOT author_key:*"),
            "searchPageUrl": build_search_page_url("NOT author_key:*"),
        },
        {
            "name": _("At least 1 edition"),
            "apiUrl": build_work_search_url("edition_count:0"),
            "searchPageUrl": build_search_page_url("edition_count:0"),
        },
        {
            "name": _("Has work (orphaned)"),
            "apiUrl": build_work_search_url("key:*M"),
            "searchPageUrl": build_search_page_url("key:*M"),
        },
        {
            "name": _("Has publication year"),
            "apiUrl": build_work_search_url("NOT publish_year:*"),
            "searchPageUrl": build_search_page_url("NOT publish_year:*"),
        },
        {
            "name": _("Has cover"),
            "apiUrl": build_work_search_url("NOT cover_i:*"),
            "searchPageUrl": build_search_page_url("NOT cover_i:*"),
        },
        {
            "name": _("Has language"),
            "apiUrl": build_work_search_url("NOT language:*"),
            "searchPageUrl": build_search_page_url("NOT language:*"),
        },
        {
            "name": _("Has publisher"),
            "apiUrl": build_work_search_url("NOT publisher:*"),
            "searchPageUrl": build_search_page_url("NOT publisher:*"),
        },
        {
            "name": _("At least 2 editions"),
            "apiUrl": build_work_search_url("edition_count:[0 TO 1]"),
            "searchPageUrl": build_search_page_url("edition_count:[0 TO 1]"),
        },
        {
            "name": _("Has dewey decimal"),
            "apiUrl": build_work_search_url("NOT ddc:*"),
            "searchPageUrl": build_search_page_url("NOT ddc:*"),
        },
        {
            "name": _("Has LoC classification"),
            "apiUrl": build_work_search_url("NOT lcc:*"),
            "searchPageUrl": build_search_page_url("NOT lcc:*"),
        },
        {
            "name": _("Has number of pages"),
            "apiUrl": build_work_search_url("OT number_of_pages_median:*"),
            "searchPageUrl": build_search_page_url("OT number_of_pages_median:*"),
        },
    ]
