"""
This file should be for internal APIs which Open Library requires for
its experience. This does not include public facing APIs with LTS
(long term support)
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Literal
from warnings import deprecated

import web

from infogami import config  # noqa: F401 side effects may be needed
from infogami.infobase.client import ClientException
from infogami.utils import delegate
from infogami.utils.view import (
    render_template,  # noqa: F401 used for its side effects
)
from openlibrary import accounts
from openlibrary.accounts.model import (
    OpenLibraryAccount,  # noqa: F401 side effects may be needed
)
from openlibrary.core import cache
from openlibrary.core.auth import ExpiredTokenError, HMACToken
from openlibrary.core.bestbook import Bestbook
from openlibrary.core.models import Booknotes
from openlibrary.core.observations import Observations
from openlibrary.core.vendors import (
    create_edition_from_amazon_metadata,
    get_amazon_metadata_async,
    get_betterworldbooks_metadata,
)
from openlibrary.i18n import gettext as _
from openlibrary.plugins.openlibrary.code import can_write
from openlibrary.plugins.openlibrary.home import get_cached_featured_subjects
from openlibrary.utils import extract_numeric_id_from_olid
from openlibrary.utils.isbn import normalize_isbn
from openlibrary.utils.request_context import req_context, site

if TYPE_CHECKING:
    from starlette.datastructures import URL

    from openlibrary.core.models import Work

logger = logging.getLogger(__name__)


class ratings:
    @staticmethod
    def get_ratings_summary(work_id):
        from openlibrary.core.ratings import Ratings

        if stats := Ratings.get_work_ratings_summary(work_id):
            return {
                "summary": {
                    "average": stats["ratings_average"],
                    "count": stats["ratings_count"],
                    "sortable": stats["ratings_sortable"],
                },
                "counts": {
                    "1": stats["ratings_count_1"],
                    "2": stats["ratings_count_2"],
                    "3": stats["ratings_count_3"],
                    "4": stats["ratings_count_4"],
                    "5": stats["ratings_count_5"],
                },
            }
        else:
            return {
                "summary": {
                    "average": None,
                    "count": 0,
                },
                "counts": {
                    "1": 0,
                    "2": 0,
                    "3": 0,
                    "4": 0,
                    "5": 0,
                },
            }


@deprecated("migrated to fastapi")
class booknotes(delegate.page):
    path = r"/works/OL(\d+)W/notes"
    encoding = "json"

    def POST(self, work_id):
        """
        Add a note to a work (or a work and an edition)
        GET params:
        - edition_id str (optional)
        - redir bool: if patron not logged in, redirect back to page after login

        :param str work_id: e.g. OL123W
        :rtype: json
        :return: the note
        """
        user = accounts.get_current_user()
        if not user:
            raise web.seeother("/account/login?redirect=/works/%s" % work_id)

        i = web.input(notes=None, edition_id=None, redir=None)
        edition_id = int(extract_numeric_id_from_olid(i.edition_id)) if i.edition_id else -1

        username = user.key.split("/")[2]

        def response(msg, status="success"):
            return delegate.RawText(json.dumps({status: msg}), content_type="application/json")

        if i.notes is None:
            Booknotes.remove(username, work_id, edition_id=edition_id)
            return response("removed note")

        Booknotes.add(username=username, work_id=work_id, notes=i.notes, edition_id=edition_id)

        if i.redir:
            raise web.seeother("/works/%s" % work_id)

        return response("note added")


def get_bookshelves_summary(work_id):
    from openlibrary.core.models import Bookshelves

    return {"counts": Bookshelves.get_work_summary(str(work_id))}


def process_work_bookshelves(username, work_id, bookshelf_id, edition_id=None, dont_remove=False):
    from openlibrary.core.models import Bookshelves

    if bookshelf_id is None:
        return {"error": "Invalid bookshelf"}

    work_id_str = str(work_id)
    current_status = Bookshelves.get_users_read_status_of_work(username, work_id_str)

    try:
        bookshelf_id_val = int(bookshelf_id)
        shelf_ids = Bookshelves.PRESET_BOOKSHELVES.values()
        if bookshelf_id_val != -1 and bookshelf_id_val not in shelf_ids:
            return {"error": "Invalid bookshelf"}
    except TypeError, ValueError:
        return {"error": "Invalid bookshelf"}

    if ((not dont_remove) and bookshelf_id_val == current_status) or bookshelf_id_val == -1:
        from openlibrary.core.bookshelves_events import BookshelvesEvents

        work_bookshelf = Bookshelves.remove(
            username=username,
            work_id=work_id_str,
            bookshelf_id=str(current_status) if current_status else None,
        )
        BookshelvesEvents.delete_by_username_and_work(username, work_id_str)
    else:
        from openlibrary.utils import extract_numeric_id_from_olid

        resolved_edition_id = int(extract_numeric_id_from_olid(edition_id)) if edition_id else None
        work_bookshelf = Bookshelves.add(
            username=username,
            bookshelf_id=str(bookshelf_id_val),
            work_id=work_id_str,
            edition_id=resolved_edition_id,
        )

    return {"bookshelves_affected": work_bookshelf}


def get_editions_data(key: str, url: URL, limit: int, offset: int) -> dict[str, Any] | None:
    current_site = site.get()
    work = current_site.get(key)
    if not work or work.type.key != "/type/work":
        return None

    limit = min(limit or 50, 1000)
    keys = current_site.things(
        {
            "type": "/type/edition",
            "works": work.key,
            "limit": limit,
            "offset": offset,
        }
    )
    editions = current_site.get_many(keys, raw=True)

    url = url.replace(scheme="", netloc="")
    links = {
        "self": str(url),
        "work": work.key,
    }
    if offset > 0:
        links["prev"] = str(url.include_query_params(offset=max(0, offset - limit)))
    if offset + len(editions) < work.edition_count:
        links["next"] = str(url.include_query_params(offset=offset + limit))

    return {"links": links, "size": work.edition_count, "entries": editions}


async def get_works_data_async(key: str, url: URL, limit: int, offset: int) -> dict[str, Any] | None:
    """Get paginated works for an author, shared by the legacy and FastAPI works.json endpoints."""
    current_site = site.get()
    author = current_site.get(key)
    if not author or author.type.key != "/type/author":
        return None

    limit = min(limit, 1000)
    keys = current_site.things(
        {
            "type": "/type/work",
            "authors": {"author": {"key": author.key}},
            "limit": limit,
            "offset": offset,
        }
    )
    works = current_site.get_many(keys, raw=True)
    size = await author.get_work_count()

    url = url.replace(scheme="", netloc="")
    links = {
        "self": str(url),
        "author": author.key,
    }
    if offset > 0:
        links["prev"] = str(url.include_query_params(offset=max(0, offset - limit)))
    if offset + len(works) < size:
        links["next"] = str(url.include_query_params(offset=offset + limit))

    return {"links": links, "size": size, "entries": works}


async def get_price_data_async(isbn: str, asin: str) -> dict[str, Any]:
    id_type_short: Literal["asin", "isbn"] = "asin" if asin else "isbn"
    id_ = asin or (normalize_isbn(isbn) or isbn)

    metadata: dict = {
        "amazon": await get_amazon_metadata_async(id_, id_type=id_type_short) or {},
        "betterworldbooks": {},
    }
    if id_type_short == "isbn":
        metadata["betterworldbooks"] = await get_betterworldbooks_metadata(id_)

    # fetch book by isbn if it exists
    # TODO: perform existing OL lookup by ASIN if supplied, if possible
    id_type_long = "asin" if asin else "isbn_13" if len(id_) == 13 else "isbn_10"
    matches = site.get().things(
        {
            "type": "/type/edition",
            id_type_long: id_,
        }
    )

    book_key = matches[0] if matches else None

    # if no OL edition for isbn, attempt to create
    if (not book_key) and metadata.get("amazon"):
        book_key = create_edition_from_amazon_metadata(id_, id_type=id_type_short)

    # include ol edition metadata in response, if available
    if book_key:
        ed = site.get().get(book_key)
        if ed:
            metadata["key"] = ed.key
            if getattr(ed, "ocaid"):  # noqa: B009
                metadata["ocaid"] = ed.ocaid

    return metadata


class patrons_observations(delegate.page):
    """
    Fetches a patron's observations for a work, requires auth, intended
    to be used internally to power the My Books Page & books pages modal
    """

    path = r"/works/OL(\d+)W/observations"
    encoding = "json"

    def GET(self, work_id):
        user = accounts.get_current_user()

        if not user:
            raise web.seeother("/account/login")

        username = user.key.split("/")[2]
        existing_records = Observations.get_patron_observations(username, work_id)

        patron_observations = defaultdict(list)

        for r in existing_records:
            kv_pair = Observations.get_key_value_pair(r["type"], r["value"])
            patron_observations[kv_pair.key].append(kv_pair.value)

        return delegate.RawText(json.dumps(patron_observations), content_type="application/json")

    def POST(self, work_id):
        user = accounts.get_current_user()

        if not user:
            raise web.seeother("/account/login")

        data = json.loads(web.data())

        Observations.persist_observation(data["username"], work_id, data["observation"], data["action"])

        def response(msg, status="success"):
            return delegate.RawText(json.dumps({status: msg}), content_type="application/json")

        return response("Observations added")

    def DELETE(self, work_id):
        user = accounts.get_current_user()
        username = user.key.split("/")[2]

        if not user:
            raise web.seeother("/account/login")

        Observations.remove_observations(username, work_id)

        def response(msg, status="success"):
            return delegate.RawText(json.dumps({status: msg}), content_type="application/json")

        return response("Observations removed")


class work_delete(delegate.page):
    path = r"/works/(OL\d+W)/[^/]+/delete"

    def get_editions_of_work(self, work: Work) -> list[dict]:
        i = web.input(bulk=False)
        limit = 1_000  # This is the max limit of the things function
        all_keys: list = []
        offset = 0

        while True:
            keys: list = web.ctx.site.things(
                {
                    "type": "/type/edition",
                    "works": work.key,
                    "limit": limit,
                    "offset": offset,
                }
            )
            all_keys.extend(keys)
            if len(keys) == limit:
                if not i.bulk:
                    raise web.HTTPError(
                        "400 Bad Request",
                        data=json.dumps(
                            {
                                "error": f"API can only delete {limit} editions per work.",
                            }
                        ),
                        headers={"Content-Type": "application/json"},
                    )
                else:
                    offset += limit
            else:
                break

        return web.ctx.site.get_many(all_keys, raw=True)

    def POST(self, work_id: str):
        if not can_write():
            return web.HTTPError("403 Forbidden")

        web_input = web.input(comment=None)

        comment = web_input.get("comment")

        work: Work = web.ctx.site.get(f"/works/{work_id}")
        if work is None:
            return web.HTTPError(status="404 Not Found")

        editions: list[dict] = self.get_editions_of_work(work)
        keys_to_delete: list = [el.get("key") for el in [*editions, work.dict()]]
        delete_payload: list[dict] = [{"key": key, "type": {"key": "/type/delete"}} for key in keys_to_delete]

        web.ctx.site.save_many(delete_payload, comment, action="bulk-delete-books")
        return delegate.RawText(
            json.dumps(
                {
                    "status": "ok",
                }
            ),
            content_type="application/json",
        )


class bestbook_award:
    """Legacy helper for the FastAPI bestbook award endpoints.

    The POST /works/OL{work_id}W/awards.json endpoint is served by FastAPI
    (openlibrary/fastapi/internal/api.py) and reuses this helper.
    """

    @staticmethod
    def process_bestbook_award(work_id, op, edition_key, topic, comment, username):
        OPS = ["add", "remove", "update"]
        edition_id = edition_key and int(extract_numeric_id_from_olid(edition_key))
        errors = []

        if username:
            try:
                if op in ["add", "update"]:
                    # Make sure the topic is free
                    if op == "update":
                        Bestbook.remove(username, topic=topic)
                        Bestbook.remove(username, work_id=work_id)
                    return {
                        "success": True,
                        "award": Bestbook.add(
                            username=username,
                            work_id=work_id,
                            edition_id=edition_id or None,
                            comment=comment,
                            topic=topic,
                        ),
                    }
                elif op == "remove":
                    # Remove any award this patron has given this work_id
                    return {
                        "success": True,
                        "rows": Bestbook.remove(username, work_id=work_id),
                    }
                else:
                    errors.append(f"Invalid op {op}: valid ops are {OPS}")
            except Bestbook.AwardConditionsError as e:
                errors.append(str(e))
        else:
            errors.append("Authentication failed")
        return {"errors": ", ".join(errors)}


def get_opds_data_provider():
    from pyopds2_openlibrary import OpenLibraryDataProvider

    provider = OpenLibraryDataProvider()
    protocol = "https" if "localhost" not in web.ctx.host else "http"
    OpenLibraryDataProvider.BASE_URL = f"{protocol}://{web.ctx.host}"
    OpenLibraryDataProvider.SEARCH_URL = "/opds/search"
    return provider


class opds_search(delegate.page):
    path = r"/opds/search"

    def GET(self):
        from pyopds2 import Catalog, Link, Metadata

        i = web.input(
            query="trending_score_hourly_sum:[1 TO *]",
            limit=25,
            page=1,
            sort=None,
            mode="ebooks",
        )

        provider = get_opds_data_provider()
        catalog = Catalog.create(
            metadata=Metadata(title=_("Search Results")),
            response=provider.search(
                query=i.query,
                limit=int(i.limit),
                offset=(int(i.page) - 1) * int(i.limit),
                sort=i.sort,
                facets={"mode": i.mode},
            ),
            links=[
                Link(
                    rel="self",
                    href=provider.BASE_URL + web.ctx.fullpath,
                    type="application/opds+json",
                ),
                Link(
                    rel="search",
                    href=f"{provider.BASE_URL}/opds/search{{?query,mode}}",
                    type="application/opds+json",
                    templated=True,
                ),
                Link(
                    rel="http://opds-spec.org/shelf",
                    href="https://archive.org/services/loans/loan/?action=user_bookshelf",
                    type="application/opds+json",
                ),
                Link(
                    rel="profile",
                    href="https://archive.org/services/loans/loan/?action=user_profile",
                    type="application/opds-profile+json",
                ),
            ],
        )
        web.header("Content-Type", "application/opds+json")
        return delegate.RawText(json.dumps(catalog.model_dump()))


class opds_books(delegate.page):
    path = r"/opds/books/(OL\d+M)"

    def GET(self, edition_olid: str):

        provider = get_opds_data_provider()
        resp = provider.search(query=f"edition_key:{edition_olid}")
        web.header("Content-Type", "application/opds-publication+json")
        if not resp.records:
            raise web.HTTPError(
                "404 Not Found",
                data=json.dumps({"error": "Edition not found"}),
            )

        pub = resp.records[0].to_publication()
        return delegate.RawText(json.dumps(pub.model_dump()))


class opds_home(delegate.page):
    path = r"/opds"

    def GET(self):
        def build_homepage():
            from pyopds2 import Catalog, Link, Metadata, Navigation

            provider = get_opds_data_provider()
            catalog = Catalog(
                metadata=Metadata(title=_("Open Library")),
                publications=[],
                navigation=[
                    Navigation(
                        type="application/opds+json",
                        title=subject["presentable_name"],
                        href=f'{provider.BASE_URL}{provider.SEARCH_URL}?sort=trending&query=subject_key:{subject["key"].split("/")[-1]} -subject:"content_warning:cover" ebook_access:[borrowable TO *]',  # noqa: E501
                    )
                    for subject in get_cached_featured_subjects()
                ],
                groups=[
                    Catalog.create(
                        metadata=Metadata(title=_("Trending Books")),
                        response=provider.search(
                            query='trending_score_hourly_sum:[1 TO *] -subject:"content_warning:cover" ebook_access:[borrowable TO *] readinglog_count:[4 TO *]',
                            sort="trending",
                            limit=25,
                        ),
                    ),
                    Catalog.create(
                        metadata=Metadata(title=_("Classic Books")),
                        response=provider.search(
                            query='ddc:8* first_publish_year:[* TO 1950] publish_year:[2000 TO *] NOT public_scan_b:false -subject:"content_warning:cover"',
                            sort="trending",
                            limit=25,
                        ),
                    ),
                    Catalog.create(
                        metadata=Metadata(title=_("Romance")),
                        response=provider.search(
                            query='subject:romance ebook_access:[borrowable TO *] first_publish_year:[1930 TO *] trending_score_hourly_sum:[1 TO *] -subject:"content_warning:cover"',  # noqa: E501
                            sort="trending,trending_score_hourly_sum",
                            limit=25,
                        ),
                    ),
                    Catalog.create(
                        metadata=Metadata(title=_("Kids")),
                        response=provider.search(
                            query='ebook_access:[borrowable TO *] trending_score_hourly_sum:[1 TO *] (subject_key:(juvenile_audience OR children\'s_fiction OR juvenile_nonfiction OR juvenile_encyclopedias OR juvenile_riddles OR juvenile_poetry OR juvenile_wit_and_humor OR juvenile_limericks OR juvenile_dictionaries OR juvenile_non-fiction) OR subject:("Juvenile literature" OR "Juvenile fiction" OR "pour la jeunesse" OR "pour enfants"))',  # noqa: E501
                            sort="random.hourly",
                            limit=25,
                        ),
                    ),
                    Catalog.create(
                        metadata=Metadata(title=_("Thrillers")),
                        response=provider.search(
                            query='subject:thrillers ebook_access:[borrowable TO *] trending_score_hourly_sum:[1 TO *] -subject:"content_warning:cover"',
                            sort="trending,trending_score_hourly_sum",
                            limit=25,
                        ),
                    ),
                    Catalog.create(
                        metadata=Metadata(title=_("Textbooks")),
                        response=provider.search(
                            query="subject_key:textbooks publish_year:[1990 TO *] ebook_access:[borrowable TO *]",
                            sort="trending",
                            limit=25,
                        ),
                    ),
                ],
                facets=None,
                links=[
                    Link(
                        rel="self",
                        href=provider.BASE_URL + web.ctx.fullpath,
                        type="application/opds+json",
                    ),
                    Link(
                        rel="start",
                        href=provider.BASE_URL,
                        type="application/opds+json",
                    ),
                    Link(
                        rel="search",
                        href=f"{provider.BASE_URL}/opds/search{{?query}}",
                        type="application/opds+json",
                        templated=True,
                    ),
                    Link(
                        rel="http://opds-spec.org/shelf",
                        href="https://archive.org/services/loans/loan/?action=user_bookshelf",
                        type="application/opds+json",
                    ),
                    Link(
                        rel="profile",
                        href="https://archive.org/services/loans/loan/?action=user_profile",
                        type="application/opds-profile+json",
                    ),
                ],
            )
            return catalog.model_dump()

        def get_cached_homepage():
            from openlibrary.plugins.openlibrary.code import is_bot
            from openlibrary.utils import dateutil
            from openlibrary.utils.request_context import caching_prethread

            five_minutes = 5 * dateutil.MINUTE_SECS
            lang = web.ctx.lang
            key = f"home.homepage-opds.{lang}"
            ctx = req_context.get()
            if ctx.print_disabled:
                key += ".pd"
            if ctx.sfw:
                key += ".sfw"
            if is_bot():
                key += ".bot"

            mc = cache.memcache_memoize(build_homepage, key, timeout=five_minutes, prethread=caching_prethread())
            page = mc()

            if not page:
                mc.memcache_delete_by_args()
                mc()

            return page

        web.header("Content-Type", "application/opds+json")
        return delegate.RawText(json.dumps(get_cached_homepage()))


DEFAULT_UNLINK_COMMENT = "Unlink OCAID: Item no longer available"


class unlink_ia_ol(delegate.page):
    path = "/api/unlink"
    encoding = "json"

    def POST(self):
        i = web.input(digest="", msg="", comment="")

        digest = i.digest
        msg = i.msg

        try:
            if not HMACToken.verify(digest, msg, "ia_sync_secret", unix_time=True):
                raise web.HTTPError("401 Unauthorized", {"Content-Type": "application/json"})
        except ValueError, ExpiredTokenError:
            raise web.HTTPError("401 Unauthorized", {"Content-Type": "application/json"})

        parts = msg.split("|", maxsplit=1)
        if len(parts) != 2 or not all(parts):
            raise web.HTTPError(
                "400 Bad Request",
                {"Content-Type": "application/json"},
                data=json.dumps({"error": "Invalid inputs"}),
            )
        ocaid, _ts = parts

        # Fetch affected editions
        edition_keys = web.ctx.site.things({"type": "/type/edition", "ocaid": ocaid})
        edition_keys.extend(web.ctx.site.things({"type": "/type/edition", "source_records": f"ia:{ocaid}"}))
        edition_keys = list(set(edition_keys))
        if not edition_keys:
            raise web.HTTPError("404 Not Found", {"Content-Type": "application/json"})

        editions = [web.ctx.site.get(key) for key in edition_keys]
        logger.info(f"Disassociating {ocaid} from the following editions: {', '.join(edition_keys)}")

        # Update records
        try:
            for edition in editions:
                self.make_dark(edition, ocaid, i.comment)
        except ClientException as e:
            logger.error(f"Failed to disassociate record with key {edition.key}", exc_info=True)
            raise web.HTTPError(
                "500 Internal Server Error",
                {"Content-Type": "application/json"},
                data=json.dumps({"error": str(e)}),
            )

        return delegate.RawText(json.dumps({"status": "ok"}))

    @staticmethod
    def make_dark(edition, ocaid, comment=""):
        data = edition.dict()
        if "ocaid" in data and data["ocaid"] == ocaid:
            del data["ocaid"]
        source_records = data.get("source_records", [])
        data["source_records"] = [rec for rec in source_records if rec != f"ia:{ocaid}"]
        if not data["source_records"]:
            del data["source_records"]
        with accounts.RunAs("ImportBot"):
            web.ctx.ip = web.ctx.ip or "127.0.0.1"
            web.ctx.site.save(
                data,
                comment or DEFAULT_UNLINK_COMMENT,
                action="edit-edition-ocaid",
            )
