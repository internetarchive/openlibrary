"""Module for providing core functionality of lending on Open Library."""

from __future__ import annotations  # Needed for 'Loan' return types early on

import logging
import os
import time
from typing import TYPE_CHECKING, Literal, TypedDict, cast

import eventer
import httpx
import requests
import web
from simplejson.errors import JSONDecodeError

from infogami.utils import delegate
from infogami.utils.view import public
from openlibrary.accounts.model import OpenLibraryAccount, parse_s3_cookie
from openlibrary.core import cache, stats
from openlibrary.core.env import get_ol_env
from openlibrary.plugins.upstream.utils import urlencode
from openlibrary.utils import dateutil, uniq
from openlibrary.utils.async_utils import async_bridge
from openlibrary.utils.request_context import (
    req_context,
    set_context_from_legacy_web_py,
    site,
)

from . import helpers as h
from . import ia

if TYPE_CHECKING:
    from openlibrary.book_providers import EbookAccess
    from openlibrary.plugins.upstream.models import Edition

    from .waitinglist import WaitingLoan


logger = logging.getLogger(__name__)

S3_LOAN_URL = "https://%s/services/loans/loan/"

DEFAULT_IA_RESULTS = 42


class PatronAccessException(Exception):
    def __init__(self, message="Access to this item is temporarily locked."):
        self.message = message
        super().__init__(self.message)


class AvailabilityServiceError(Exception):
    pass


config_ia_loan_api_url = None
config_ia_xauth_api_url = None
config_ia_availability_api_v2_url = cast(str, None)
config_ia_access_secret = None
config_ia_domain = None
config_ia_ol_shared_key = None
config_ia_ol_xauth_s3 = None
config_ia_s3_auth_url = None
config_ia_ol_metadata_write_s3 = None
config_ia_users_loan_history = None
config_ia_loan_api_developer_key = None
config_http_request_timeout = None
config_bookreader_host = None
config_internal_tests_api_key = None
config_fts_context = None
config_ia_s3_loan_url = None  # S3-based loan endpoint; falls back to S3_LOAN_URL % bookreader_host


def setup(config):
    """Initializes this module from openlibrary config."""
    global config_ia_access_secret, config_bookreader_host
    global config_ia_ol_shared_key, config_ia_ol_xauth_s3, config_internal_tests_api_key
    global config_ia_loan_api_url, config_http_request_timeout
    global config_ia_availability_api_v2_url, config_ia_ol_metadata_write_s3
    global config_ia_xauth_api_url, config_http_request_timeout, config_ia_s3_auth_url
    global config_ia_users_loan_history, config_ia_loan_api_developer_key
    global config_ia_domain, config_fts_context, config_ia_s3_loan_url

    config_bookreader_host = config.get("bookreader_host", "archive.org")
    config_ia_domain = config.get("ia_base_url", "https://archive.org")
    config_ia_loan_api_url = config.get("ia_loan_api_url")
    config_ia_s3_loan_url = config.get("ia_s3_loan_url")
    config_ia_availability_api_v2_url = cast(str, config.get("ia_availability_api_v2_url"))
    config_ia_xauth_api_url = config.get("ia_xauth_api_url")
    config_ia_access_secret = config.get("ia_access_secret")
    config_ia_ol_shared_key = config.get("ia_ol_shared_key")
    config_ia_ol_xauth_s3 = config.get("ia_ol_xauth_s3")
    config_ia_ol_metadata_write_s3 = config.get("ia_ol_metadata_write_s3")
    config_ia_s3_auth_url = config.get("ia_s3_auth_url")
    config_ia_users_loan_history = config.get("ia_users_loan_history")
    config_ia_loan_api_developer_key = config.get("ia_loan_api_developer_key")
    config_internal_tests_api_key = config.get("internal_tests_api_key")
    config_http_request_timeout = config.get("http_request_timeout")
    config_fts_context = config.get("fts_context")


@public
def compose_ia_url(
    limit: int | None = None,
    page: int = 1,
    subject=None,
    query=None,
    sorts=None,
    advanced: bool = True,
    safe_mode: bool = False,
) -> str | None:
    """This needs to be exposed by a generalized API endpoint within
    plugins/api/browse which lets lazy-load more items for
    the homepage carousel and support the upcoming /browse view
    (backed by archive.org search, so we don't have to send users to
    archive.org to see more books)

    Returns None if we get an empty query
    """
    from openlibrary.core.carousels import CAROUSELS_PRESETS

    query = CAROUSELS_PRESETS.get(query, query)
    q = "openlibrary_work:(*)"

    # If we don't provide an openlibrary_subject and no collection is
    # specified in our query, we restrict our query to the `inlibrary`
    # collection (i.e. those books which are borrowable)
    if (not subject) and (not query or "collection:" not in query):
        q += " AND collection:(inlibrary)"
    # In the only case where we are not restricting our search to
    # borrowable books (i.e. `inlibrary`), we remove all the books
    # which are `printdisabled` *outside* of `inlibrary`.
    if "collection:(inlibrary)" not in q:
        q += " AND (collection:(inlibrary) OR (!collection:(printdisabled)))"

    # If no lending restrictions (e.g. borrow, read) are imposed in
    # our query, we assume only borrowable books will be included in
    # results (not unrestricted/open books).
    lendable = "(lending___available_to_browse:true OR lending___available_to_borrow:true)"
    if (not query) or lendable not in query:
        q += " AND " + lendable
    if query:
        q += " AND " + query
    if subject:
        q += " AND openlibrary_subject:" + subject

    if safe_mode:
        q += " AND !collection:(no-preview)"

    if not advanced:
        _sort = sorts[0] if sorts else ""
        if " desc" in _sort:
            _sort = "-" + _sort.split(" desc")[0]
        elif " asc" in _sort:
            _sort = _sort.split(" asc")[0]
        simple_params = {"query": q}
        if _sort:
            simple_params["sort"] = _sort
        return "https://archive.org/search.php?" + urlencode(simple_params)

    rows = limit or DEFAULT_IA_RESULTS
    params = [
        ("q", q),
        ("fl[]", "identifier"),
        ("fl[]", "openlibrary_edition"),
        ("fl[]", "openlibrary_work"),
        ("rows", rows),
        ("page", page),
        ("output", "json"),
    ]
    if not get_ol_env().LOCAL_DEV:
        # This flag is only available on prod
        params.append(("service", "metadata__unlimited"))
    if not sorts or not isinstance(sorts, list):
        sorts = [""]
    for sort in sorts:
        params.append(("sort[]", sort))
    base_url = f"http://{config_bookreader_host}/advancedsearch.php"
    return base_url + "?" + urlencode(params)


@cache.memoize(engine="memcache", key="gt-availability", expires=5 * dateutil.MINUTE_SECS)
def get_cached_groundtruth_availability(ocaid):
    return get_groundtruth_availability(ocaid)


async def get_groundtruth_availability_async(ocaid, s3_keys=None):
    """temporary stopgap to get ground-truth availability of books
    including 1-hour borrows"""
    params = "?action=availability&identifier=" + ocaid
    url = config_ia_s3_loan_url or S3_LOAN_URL % config_bookreader_host
    timeout = 2 if os.getenv("LOCAL_DEV") else config_http_request_timeout
    try:
        response = await ia.get_async_session().post(url + params, data=s3_keys, timeout=timeout)
        response.raise_for_status()
    except httpx.TimeoutException:
        if os.getenv("LOCAL_DEV"):
            logger.warning("Availability request timed out in LOCAL_DEV environment. Returning empty dictionary.")
            return {}
        else:
            logger.error("Availability request timed out in non-LOCAL_DEV environment. Re-raising the exception.")
            raise  # Re-raise the timeout exception if not in LOCAL_DEV
    except httpx.HTTPError:
        pass  # TODO: Handle unexpected responses from the availability server.
    try:
        data = response.json().get("lending_status", {})
    except JSONDecodeError:
        data = {}
    # For debugging
    data["__src__"] = "core.models.lending.get_groundtruth_availability"
    return data


get_groundtruth_availability = async_bridge.wrap(get_groundtruth_availability_async)


async def s3_loan_api_async(s3_keys, ocaid=None, action="browse", **kwargs):
    """Uses patrons s3 credentials to initiate or return a browse or
    borrow loan on Archive.org.

    :param dict s3_keys: {'access': 'xxx', 'secret': 'xxx'}
    :param str  action : 'browse_book' or 'borrow_book' or 'return_loan'
    :param dict kwargs   : Additional data to be sent in the POST request body (limit, offset)

    """
    fields = {"identifier": ocaid, "action": action}
    params = "?" + "&".join([f"{k}={v}" for (k, v) in fields.items() if v])
    url = config_ia_s3_loan_url or S3_LOAN_URL % config_bookreader_host

    data = s3_keys | kwargs

    response = await ia.get_async_session().post(url + params, data=data, timeout=config_http_request_timeout)
    # We want this to be just `409` but first
    # `www/common/Lending.inc#L111-114` needs to
    # be updated on petabox
    if response.status_code in [400, 409]:
        raise PatronAccessException
    response.raise_for_status()
    return response


s3_loan_api = async_bridge.wrap(s3_loan_api_async)


async def get_available_async(
    limit=None,
    page=1,
    subject=None,
    query=None,
    sorts=None,
    url=None,
    safe_mode=False,
):
    """Experimental. Retrieves a list of available editions from
    archive.org advancedsearch which are available, in the inlibrary
    collection, and optionally apart of an `openlibrary_subject`.

    Returns a list of editions (one available edition per work). Is
    used in such things as 'Staff Picks' carousel to retrieve a list
    of unique available books.
    """

    url = url or compose_ia_url(
        limit=limit,
        page=page,
        subject=subject,
        query=query,
        sorts=sorts,
        safe_mode=safe_mode,
    )
    if not url:
        logger.error(
            "get_available failed",
            extra={
                "limit": limit,
                "page": page,
                "subject": subject,
                "query": query,
                "sorts": sorts,
            },
        )
        return {"error": "no_url"}
    try:
        # Internet Archive Elastic Search (which powers some of our
        # carousel queries) needs Open Library to forward user IPs so
        # we can attribute requests to end-users
        req = req_context.get(None)
        client_ip = req.x_forwarded_for if req and req.x_forwarded_for else "ol-internal"
        headers = {
            "x-client-id": client_ip,
            "x-preferred-client-id": client_ip,
            "x-application-id": "openlibrary",
        }
        response = await ia.get_async_session().get(url, headers=headers, timeout=config_http_request_timeout)
        items = response.json().get("response", {}).get("docs", [])
        results = {}
        for item in items:
            if item.get("openlibrary_work"):
                results[item["openlibrary_work"]] = item["openlibrary_edition"]
        books = site.get().get_many([f"/books/{olid}" for olid in results.values()])
        books = await add_availability_async(books)
        return books
    except Exception:  # TODO: Narrow exception scope
        logger.exception(f"get_available({url})")
        return {"error": "request_timeout"}


# Create a sync wrapper for backward compatibility
get_available = async_bridge.wrap(get_available_async)


class AvailabilityStatus(TypedDict):
    status: Literal["borrow_available", "borrow_unavailable", "open", "error"]
    error_message: str | None
    available_to_browse: bool | None
    available_to_borrow: bool | None
    available_to_waitlist: bool | None
    is_printdisabled: bool | None
    is_readable: bool | None
    is_lendable: bool | None
    is_previewable: bool

    identifier: str | None
    isbn: str | None
    oclc: str | None
    openlibrary_work: str | None
    openlibrary_edition: str | None

    last_loan_date: str | None
    """e.g. 2020-07-31T19:07:55Z"""

    num_waitlist: str | None
    """A number represented inexplicably as a string"""

    last_waitlist_date: str | None
    """e.g. 2020-07-31T19:07:55Z"""


class AvailabilityServiceResponse(TypedDict):
    success: bool
    error: str | None
    responses: dict[str, AvailabilityStatus]


class AvailabilityStatusV2(AvailabilityStatus):
    is_restricted: bool
    is_browseable: bool | None
    __src__: str


def get_ebook_access_availability(ocaid: str, ebook_access: EbookAccess) -> AvailabilityStatusV2:
    from openlibrary.book_providers import EbookAccess

    status: Literal["borrow_available", "borrow_unavailable", "open", "error"] = "error"
    if ebook_access == EbookAccess.BORROWABLE:
        status = "borrow_available"
    elif ebook_access == EbookAccess.PUBLIC:
        status = "open"
    return {
        "status": status,
        "error_message": None,
        "available_to_browse": ebook_access == EbookAccess.BORROWABLE,
        "available_to_borrow": ebook_access == EbookAccess.BORROWABLE,
        "available_to_waitlist": False,
        "is_printdisabled": ebook_access >= EbookAccess.PRINTDISABLED,
        "is_readable": ebook_access == EbookAccess.PUBLIC,
        "is_lendable": ebook_access == EbookAccess.BORROWABLE,
        "is_previewable": ebook_access >= EbookAccess.PRINTDISABLED,
        "identifier": ocaid,
        "isbn": None,
        "oclc": None,
        "openlibrary_work": None,
        "openlibrary_edition": None,
        "last_loan_date": None,
        "num_waitlist": None,
        "last_waitlist_date": None,
        "is_restricted": ebook_access <= EbookAccess.BORROWABLE,
        "is_browseable": ebook_access == EbookAccess.BORROWABLE,
        "__src__": "core.models.lending.get_ebook_access_availability",
    }


def update_availability_schema_to_v2(
    v1_resp: AvailabilityStatus,
    ocaid: str | None,
) -> AvailabilityStatusV2:
    """
    This function attempts to take the output of e.g. Bulk Availability
    API and add/infer attributes which are missing (but are present on
    Ground Truth API)
    """
    v2_resp = cast(AvailabilityStatusV2, v1_resp)
    # TODO: Make less brittle; maybe add simplelists/copy counts to Bulk Availability
    v2_resp["identifier"] = ocaid
    v2_resp["is_restricted"] = v1_resp["status"] != "open"
    v2_resp["is_browseable"] = v1_resp.get("available_to_browse", False)
    # For debugging
    v2_resp["__src__"] = "core.models.lending.get_availability"
    return v2_resp


async def get_availability_async(
    id_type: Literal["identifier", "openlibrary_work", "openlibrary_edition"],
    ids: list[str],
) -> dict[str, AvailabilityStatusV2]:
    ids = [id_ for id_ in ids if id_]  # remove infogami.infobase.client.Nothing
    if not ids:
        return {}

    def key_func(_id: str) -> str:
        return cache.build_memcache_key("lending.get_availability", id_type, _id)

    mc = cache.get_memcache()

    cached_values = cast(dict[str, AvailabilityStatusV2], mc.get_multi([key_func(_id) for _id in ids]))
    availabilities = {_id: cached_values[key] for _id in ids if (key := key_func(_id)) in cached_values}
    ids_to_fetch = set(ids) - set(availabilities)

    if not ids_to_fetch:
        return availabilities

    try:
        headers = {
            "x-preferred-client-id": req_context.get().x_forwarded_for or "ol-internal",
            "x-preferred-client-useragent": req_context.get().user_agent or "",
            "x-application-id": "openlibrary",
            "user-agent": "Open Library Site",
        }
        if config_ia_ol_metadata_write_s3:
            headers["authorization"] = "LOW {s3_key}:{s3_secret}".format(**config_ia_ol_metadata_write_s3)
        resp = await ia.get_async_session().get(
            config_ia_availability_api_v2_url,
            params={
                id_type: ",".join(ids_to_fetch),
                "scope": "printdisabled",
            },
            headers=headers,
            timeout=config_http_request_timeout,
        )

        # This API should always return 200
        resp.raise_for_status()

        response = cast(AvailabilityServiceResponse, resp.json())

        if not response["success"]:
            logger.warning(f"AvailabilityServiceError: {response['error']}")
            stats.increment("ol.availability.service_error", rate=0.01)
            return {}

        uncached_values = {
            _id: update_availability_schema_to_v2(
                availability,
                ocaid=(_id if id_type == "identifier" else availability.get("identifier")),
            )
            for _id, availability in response["responses"].items()
        }
        availabilities |= uncached_values
        mc.set_multi(
            {key_func(_id): availability for _id, availability in uncached_values.items()},
            expires=5 * dateutil.MINUTE_SECS,
        )
        return availabilities
    except Exception as e:  # TODO: Narrow exception scope
        logger.exception("lending.get_availability", extra={"ids": ids})
        availabilities.update(
            {
                _id: update_availability_schema_to_v2(
                    cast(AvailabilityStatus, {"status": "error"}),
                    ocaid=_id if id_type == "identifier" else None,
                )
                for _id in ids_to_fetch
            }
        )
        return availabilities | {
            "error": "request_timeout",
            "details": str(e),
        }  # type: ignore


get_availability = async_bridge.wrap(get_availability_async)


def get_ocaid(item: dict) -> str | None:
    # Circular import otherwise
    from ..book_providers import is_non_ia_ocaid

    possible_fields = [
        "ocaid",  # In editions
        "identifier",  # In ?? not editions/works/solr
        "ia",  # In solr work records and worksearch get_docs
        "lending_identifier",  # In solr works records + worksearch get_doc
    ]
    # SOLR WORK RECORDS ONLY:
    # Open Library only has access to a list of archive.org IDs
    # and solr isn't currently equipped with the information
    # necessary to determine which editions may be openly
    # available. Using public domain date as a heuristic
    # Long term solution is a full reindex, but this hack will work in the
    # vast majority of cases for now.
    # NOTE: there is still a risk pre-1923 books will get a print-diabled-only
    # or lendable edition.
    # Note: guaranteed to be int-able if none None
    US_PD_YEAR = 1923
    if float(item.get("first_publish_year") or "-inf") > US_PD_YEAR:
        # Prefer `lending_identifier` over `ia` (push `ia` to bottom)
        possible_fields.remove("ia")
        possible_fields.append("ia")

    ocaids: list[str] = []
    for field in possible_fields:
        if item.get(field):
            val = cast(list[str] | str, item[field])
            ocaids += val if isinstance(val, list) else [val]
    ocaids = uniq(ocaids)
    return next((ocaid for ocaid in ocaids if not is_non_ia_ocaid(ocaid)), None)


def get_availabilities(items: list) -> dict:
    result = {}
    ocaids = [ocaid for ocaid in map(get_ocaid, items) if ocaid]
    availabilities = get_availability("identifier", ocaids)
    for item in items:
        ocaid = get_ocaid(item)
        if ocaid:
            result[item["key"]] = availabilities.get(ocaid)
    return result


async def add_availability_async(
    items: list,
    mode: Literal["identifier", "openlibrary_work"] = "identifier",
) -> list:
    """
    Adds API v2 'availability' key to dicts
    :param items: items with fields containing ocaids
    """
    if mode == "identifier":
        from openlibrary.book_providers import EbookAccess
        from openlibrary.plugins.openlibrary.code import is_bot

        if is_bot() and items and "ebook_access" in items[0]:
            for item in items:
                ocaid = get_ocaid(item)
                if ocaid:
                    item["availability"] = get_ebook_access_availability(ocaid, EbookAccess.from_solr_str(item["ebook_access"]))
        else:
            ocaids = [ocaid for ocaid in map(get_ocaid, items) if ocaid]
            availabilities = await get_availability_async("identifier", ocaids)
            for item in items:
                ocaid = get_ocaid(item)
                if ocaid:
                    item["availability"] = availabilities.get(ocaid)
    elif mode == "openlibrary_work":
        _ids = [item["key"].split("/")[-1] for item in items]
        availabilities = await get_availability_async("openlibrary_work", _ids)
        for item in items:
            olid = item["key"].split("/")[-1]
            if olid:
                item["availability"] = availabilities.get(olid)
    return items


add_availability = async_bridge.wrap(add_availability_async, "add_availability")


def get_items_and_add_availability(ocaids: list[str]) -> dict[str, Edition]:
    """
    Get Editions from OCAIDs and attach their availabiliity.

    Returns a dict of the form: `{"ocaid1": edition1, "ocaid2": edition2, ...}`
    """
    ocaid_availability = get_availability("identifier", ocaids)
    editions = site.get().get_many([f"/books/{item.get('openlibrary_edition')}" for item in ocaid_availability.values() if item.get("openlibrary_edition")])

    # Attach availability
    for edition in editions:
        if edition.ocaid in ocaids:
            edition.availability = ocaid_availability.get(edition.ocaid)

    return {edition.ocaid: edition for edition in editions if edition.ocaid}


def is_loaned_out(identifier: str) -> bool:
    """Returns True if the given identifier is loaned out.

    This doesn't worry about waiting lists.
    """
    return bool(get_loan(identifier)) or (is_loaned_out_on_ia(identifier) is True)


def is_loaned_out_on_ia(identifier: str) -> bool | None:
    """Returns True if the item is checked out on Internet Archive."""
    url = f"https://archive.org/services/borrow/{identifier}?action=status"
    try:
        response = ia.session.get(url, timeout=config_http_request_timeout).json()
        return response and response.get("checkedout")
    except Exception:  # TODO: Narrow exception scope
        logger.exception(f"is_loaned_out_on_ia({identifier})")
        return None


def get_loan(identifier: str, user_key: str | None = None):
    """Returns the loan object for given identifier, if a loan exists.

    If user_key is specified, it returns the loan only if that user is
    borrowed that book.
    """
    _loan = None
    account = None
    if user_key:
        if user_key.startswith("@"):
            account = OpenLibraryAccount.get_by_link(user_key)
        else:
            account = OpenLibraryAccount.get_by_key(user_key)

    try:
        _loan = _get_ia_loan(identifier, account and userkey2userid(account.username))
    except Exception:  # TODO: Narrow exception scope
        logger.exception(f"get_loan({identifier}) 1 of 2")

    try:
        _loan = _get_ia_loan(identifier, account and account.itemname)
    except Exception:  # TODO: Narrow exception scope
        logger.exception(f"get_loan({identifier}) 2 of 2")

    return _loan


def _get_ia_loan(identifier: str, userid: str | None = None):
    ia_loan = ia_lending_api.get_loan(identifier, userid)
    return ia_loan and Loan.from_ia_loan(ia_loan)


def get_loans_of_user(user_key: str) -> list[Loan]:
    if "env" not in web.ctx:
        """For the get_cached_user_loans to call the API if no cache is present,
        we have to fakeload the web.ctx
        """
        delegate.fakeload()
        set_context_from_legacy_web_py()

    account = OpenLibraryAccount.get_by_username(user_key.rsplit("/", maxsplit=1)[-1])

    loans = []
    if account and account.itemname:
        ia_loans = ia_lending_api.find_loans(userid=account.itemname)
        loans = [Loan.from_ia_loan(d) for d in ia_loans]
    # Set patron's loans in cache w/ now timestamp
    get_cached_loans_of_user.memcache_set((user_key,), {}, loans or [], time.time())  # rehydrate cache
    return loans


get_cached_loans_of_user = cache.memcache_memoize(
    get_loans_of_user,
    key_prefix="lending.cached_loans",
    timeout=5 * dateutil.MINUTE_SECS,  # time to live for cached loans = 5 minutes
)


def get_user_waiting_loans(user_key: str) -> list[WaitingLoan]:
    """Gets the waitingloans of the patron.

    Returns [] if user has no waitingloans.
    """
    from .waitinglist import WaitingLoan

    if "site" not in web.ctx:
        delegate.fakeload()

    try:
        account = OpenLibraryAccount.get_by_key(user_key)
        itemname = account.itemname if account else None
        result = WaitingLoan.query(userid=itemname)
        get_cached_user_waiting_loans.memcache_set((user_key,), {}, result or [], time.time())  # rehydrate cache
        return result or []
    except JSONDecodeError:
        return []


get_cached_user_waiting_loans = cache.memcache_memoize(
    get_user_waiting_loans,
    key_prefix="waitinglist.user_waiting_loans",
    timeout=10 * dateutil.MINUTE_SECS,
)


NOT_INITIALIZED = object()


def sync_loan(identifier, loan=NOT_INITIALIZED):
    """Updates the loan info stored in openlibrary.

    The loan records are stored at the Internet Archive. There is no way for
    OL to know when a loan is deleted. To handle that situation, the loan info
    is stored in the ebook document and the deletion is detected by comparing
    the current loan id and loan id stored in the ebook.

    This function is called whenever the loan is updated.
    """
    logger.info("BEGIN sync_loan %s %s", identifier, loan)

    if loan is NOT_INITIALIZED:
        loan = get_loan(identifier)

    # The data of the loan without the user info.
    loan_data = loan and {
        "uuid": loan["uuid"],
        "loaned_at": loan["loaned_at"],
        "resource_type": loan["resource_type"],
        "ocaid": loan["ocaid"],
        "book": loan["book"],
    }

    responses = get_availability("identifier", [identifier])
    response = responses[identifier] if responses else {}
    if response:
        num_waiting = int(response.get("num_waitlist", 0) or 0)

    ebook = EBookRecord.find(identifier)

    # The loan known to us is deleted
    is_loan_completed = ebook.get("loan") and ebook.get("loan") != loan_data

    # Only remember the loan_data if we could resolve an OL user for it
    if loan and loan["user"] is not None:
        ebook_loan_data = loan_data
    else:
        ebook_loan_data = None

    kwargs = {
        "type": "ebook",
        "identifier": identifier,
        "loan": ebook_loan_data,
        "borrowed": str(response["status"] not in ["open", "borrow_available"]).lower(),
        "wl_size": num_waiting,
    }
    try:
        ebook.update(**kwargs)
    except Exception:  # TODO: Narrow exception scope
        # updating ebook document is sometimes failing with
        # "Document update conflict" error.
        # Log the error in such cases, don't crash.
        logger.exception("failed to update ebook for %s", identifier)

    # fire loan-completed event
    if is_loan_completed and ebook.get("loan"):
        _d = dict(ebook["loan"], returned_at=time.time())
        eventer.trigger("loan-completed", _d)
    logger.info("END sync_loan %s", identifier)


class EBookRecord(dict):
    @staticmethod
    def find(identifier: str) -> EBookRecord:
        key = "ebooks/" + identifier
        d = site.get().store.get(key) or {"_key": key, "type": "ebook", "_rev": 1}
        return EBookRecord(d)

    def update(self, **kwargs):
        logger.info("updating %s %s", self["_key"], kwargs)
        # Nothing to update if what we have is same as what is being asked to
        # update.
        d = {k: self.get(k) for k in kwargs}
        if d == kwargs:
            return

        dict.update(self, **kwargs)
        site.get().store[self["_key"]] = self


class Loan(dict):
    """Model for loan."""

    @staticmethod
    def from_ia_loan(data: dict) -> Loan:
        if data["userid"].startswith("ol:"):
            user_key = "/people/" + data["userid"][len("ol:") :]
        elif data["userid"].startswith("@"):
            account = OpenLibraryAccount.get_by_link(data["userid"])
            user_key = ("/people/" + account.username) if account else None
        else:
            user_key = None

        if data["ol_key"]:
            book_key = data["ol_key"]
        else:
            book_key = resolve_identifier(data["identifier"])

        created = h.parse_datetime(data["created"])

        # For historic reasons, OL considers expiry == None as un-fulfilled
        # loan.

        expiry = data.get("until")

        d = {
            "_key": "loan-{}".format(data["identifier"]),
            "_rev": 1,
            "type": "/type/loan",
            "userid": data["userid"],
            "user": user_key,
            "book": book_key,
            "ocaid": data["identifier"],
            "expiry": expiry,
            "fulfilled": data["fulfilled"],
            "uuid": "loan-{}".format(data["id"]),
            "loaned_at": time.mktime(created.timetuple()),
            "resource_type": data["format"],
            "resource_id": data["resource_id"],
            "loan_link": data["loan_link"],
        }
        return Loan(d)


def resolve_identifier(identifier: str) -> str | None:
    """Returns the OL book key for given IA identifier."""
    if keys := site.get().things({"type": "/type/edition", "ocaid": identifier}):
        return keys[0]
    else:
        return "/books/ia:" + identifier


def userkey2userid(user_key: str) -> str:
    username = user_key.rsplit("/", maxsplit=1)[-1]
    return "ol:" + username


class IA_Lending_API:
    """Archive.org waiting list API."""

    def get_loan(self, identifier: str, userid: str | None = None):
        params = {"method": "loan.query", "identifier": identifier}
        if userid:
            params["userid"] = userid
        if loans := self._post(**params).get("result", []):
            return loans[0]

    def find_loans(self, **kw):
        try:
            return self._post(method="loan.query", **kw).get("result", [])
        except JSONDecodeError:
            return []

    def create_loan(self, identifier, userid, format, ol_key):
        response = self._post(
            method="loan.create",
            identifier=identifier,
            userid=userid,
            format=format,
            ol_key=ol_key,
        )
        if response["status"] == "ok":
            return response["result"]["loan"]

    def delete_loan(self, identifier, userid):
        self._post(method="loan.delete", identifier=identifier, userid=userid)

    def get_waitinglist_of_book(self, identifier):
        return self.query(identifier=identifier)

    def get_waitinglist_of_user(self, userid):
        return self.query(userid=userid)

    def join_waitinglist(self, identifier, userid):
        return self._post(method="waitinglist.join", identifier=identifier, userid=userid)

    def leave_waitinglist(self, identifier, userid):
        return self._post(method="waitinglist.leave", identifier=identifier, userid=userid)

    def update_waitinglist(self, identifier, userid, **kwargs):
        return self._post(method="waitinglist.update", identifier=identifier, userid=userid, **kwargs)

    def query(self, **params):
        response = self._post(method="waitinglist.query", **params)
        return response.get("result")

    def request(self, method, **arguments):
        return self._post(method=method, **arguments)

    def _post(self, **payload):
        logger.info("POST %s %s", config_ia_loan_api_url, payload)
        if config_ia_loan_api_developer_key:
            payload["developer"] = config_ia_loan_api_developer_key
        payload["token"] = config_ia_ol_shared_key

        try:
            jsontext = requests.post(
                config_ia_loan_api_url,
                data=payload,
                timeout=config_http_request_timeout,
            ).json()
            logger.info("POST response: %s", jsontext)
            return jsontext
        except JSONDecodeError:
            logger.exception("POST failed to openlibrary.php, no json")
            return {}
        except Exception:  # TODO: Narrow exception scope
            logger.exception("POST failed")
            raise


ia_lending_api = IA_Lending_API()


@public
def get_lending_state(doc, user=None, check_loan_status=False) -> str:
    """Resolves the user-facing lending/availability state of a document (Work, Edition, or Solr dict).

    Returns one of: "borrowed", "partner", "open", "printdisabled", "borrowable", "waitlist", "checkedout", "preview_only", "locate"
    """
    availability = doc.availability if hasattr(doc, "availability") else (doc.get("availability") if hasattr(doc, "get") else None)
    if not availability:
        availability = {}

    ocaid = doc.get("ocaid") if hasattr(doc, "get") else getattr(doc, "ocaid", None)
    if not ocaid and hasattr(availability, "get"):
        ocaid = availability.get("identifier")

    # 1. Cheap check: Active loan already in doc
    user_loan = doc.get("loan") if hasattr(doc, "get") else getattr(doc, "loan", None)
    if user_loan:
        return "borrowed"

    # 2. Cheap check: Book provider is not IA
    from openlibrary.book_providers import get_book_provider

    book_provider = get_book_provider(doc)
    bp_short_name = book_provider.short_name if (book_provider and hasattr(book_provider, "short_name")) else ""
    if book_provider and bp_short_name != "ia":
        return "partner"

    # 3. Cheap check: Book is open/publicly readable
    if availability.get("is_readable") or availability.get("status") == "open":
        return "open"

    # 4. Defer checking DB for user active loan
    if not user_loan and check_loan_status and ocaid:
        if user is None:
            from openlibrary.accounts import get_current_user

            user = get_current_user()
        if user:
            user_loan = user.get_loan_for(ocaid, use_cache=True)
            if user_loan:
                return "borrowed"

    # 5. Check print-disabled user
    if ocaid:
        if user is None:
            from openlibrary.accounts import get_current_user

            user = get_current_user()
        if user and user.is_printdisabled():
            return "printdisabled"

    # 6. Check lendable books
    if availability.get("is_lendable"):
        if availability.get("available_to_borrow") or availability.get("available_to_browse"):
            return "borrowable"

        is_waiting = False
        if not availability.get("available_to_waitlist") and check_loan_status and ocaid:
            if user is None:
                from openlibrary.accounts import get_current_user

                user = get_current_user()
            if user:
                waiting_loan = user.get_user_waiting_loans(ocaid, use_cache=True)
                if waiting_loan:
                    status = waiting_loan.get("status") if hasattr(waiting_loan, "get") else getattr(waiting_loan, "status", None)
                    position = waiting_loan.get("position") if hasattr(waiting_loan, "get") else getattr(waiting_loan, "position", None)
                    is_waiting = not (status == "available" and position == 1)

        if availability.get("available_to_waitlist") or is_waiting:
            return "waitlist"
        else:
            return "checkedout"

    # 7. Check previewable
    if ocaid and availability.get("is_previewable") and book_provider and bp_short_name == "ia":
        return "preview_only"

    return "locate"


RESULTS_PER_PAGE: int = 25


def get_loan_history_data(username: str, page: int) -> dict:
    """Fetch loan history data for a user.

    This will use a patron's S3 keys to query the IA loan history API,
    get the IA IDs, get the OLIDs if available, and then convert this
    into editions and IA-only items for display in the loan history.

    This returns both editions and IA-only items because the loan history API
    includes items that are not in Open Library, and displaying only IA
    items creates pagination and navigation issues. For further discussion,
    see https://github.com/internetarchive/openlibrary/pull/8375.
    """
    from infogami.utils.view import render

    if not OpenLibraryAccount.get_by_username(username):
        raise render.notfound("Account not found for %s" % username, create=False)

    s3_keys = parse_s3_cookie(web.cookies().get("s3"))
    limit = RESULTS_PER_PAGE
    offset = page * limit - limit

    # parse_s3_cookie() is `dict | None`: it returns None for a patron with no
    # `s3` session cookie. s3_loan_api() would then evaluate `s3_keys | kwargs`
    # and raise `TypeError: unsupported operand type(s) for |: 'NoneType' and 'dict'`.
    # /account/loans renders this history inline with no try/except of its own,
    # so that TypeError takes down the whole page -- including the active-loans
    # table, which has nothing to do with IA history. Degrade to an empty
    # history instead, and say so in the log rather than failing silently.
    if not s3_keys:
        logger.warning("No IA S3 keys for %s; returning empty loan history", username)
        return {"docs": [], "show_next": False, "limit": limit, "page": page}

    response = s3_loan_api(
        s3_keys=s3_keys,
        action="user_borrow_history",
        limit=limit + 1,
        offset=offset,
        newest=True,
    ).json()
    history = response.get("history") or {}
    loan_history = history.get("items") or []

    # We request limit+1 to see if there is another page of history to display,
    # and then pop the +1 off if it's present.
    show_next = len(loan_history) == limit + 1
    if show_next:
        loan_history.pop()

    ocaids = [loan_record["identifier"] for loan_record in loan_history]
    loan_history_map = {loan_record["identifier"]: loan_record for loan_record in loan_history}

    # Get editions and attach their loan history.
    editions_map = get_items_and_add_availability(ocaids=ocaids)
    for edition in editions_map.values():
        if edition_loan_history := loan_history_map.get(edition.get("ocaid")):
            edition["last_loan_date"] = edition_loan_history.get("updatedate", "")
        else:
            edition["last_loan_date"] = ""

    # Create 'placeholders' dicts for items in the Internet Archive loan history,
    # but absent from Open Library, and then add loan history.
    # ia_only['loan'] isn't set because `LoanStatus.html` reads it as a current
    # loan. No apparently way to distinguish between current and past loans with
    # this API call.
    ia_only_loans = [{"ocaid": ocaid} for ocaid in ocaids if ocaid not in editions_map]
    for ia_only_loan in ia_only_loans:
        loan_data = loan_history_map[ia_only_loan["ocaid"]]
        ia_only_loan["last_loan_date"] = loan_data.get("updatedate", "")
        ia_only_loan["ia_only"] = True  # type: ignore[typeddict-unknown-key]

    editions_and_ia_loans = list(editions_map.values()) + ia_only_loans
    editions_and_ia_loans.sort(key=lambda item: item.get("last_loan_date", ""), reverse=True)

    return {
        "docs": editions_and_ia_loans,
        "show_next": show_next,
        "limit": limit,
        "page": page,
    }
