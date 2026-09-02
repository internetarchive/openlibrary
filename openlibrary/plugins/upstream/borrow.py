"""Handlers for borrowing books"""

import contextlib
import hashlib
import hmac
import json
import logging
import time
import urllib
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import web
from markupsafe import Markup, escape
from pydantic import BaseModel, Field

from infogami import config
from infogami.infobase.utils import parse_datetime
from infogami.utils import delegate
from infogami.utils.view import (
    add_flash_message,
    public,
)
from openlibrary import accounts
from openlibrary.accounts.model import OpenLibraryAccount, parse_s3_cookie
from openlibrary.core import (
    lending,
    models,  # noqa: F401 side effects may be needed
    stats,
    vendors,
)
from openlibrary.core.jinja import render_jinja_template
from openlibrary.i18n import gettext as _
from openlibrary.utils import dateutil
from openlibrary.utils.async_utils import async_bridge
from openlibrary.utils.request_context import req_context, site

logger = logging.getLogger("openlibrary.borrow")

# ######### Constants

lending_library_subject = "Lending library"
in_library_subject = "In library"
lending_subjects = {lending_library_subject, in_library_subject}

# Max loans a user can have at once
user_max_loans = 5

# When we generate a loan offer (.acsm) for a user we assume that the loan has occurred.
# Once the loan fulfillment inside Digital Editions the book status server will know
# the loan has occurred.  We allow this timeout so that we don't delete the OL loan
# record before fulfillment because we can't find it in the book status server.
# $$$ If a user borrows an ACS4 book and immediately returns book loan will show as
#     "not yet downloaded" for the duration of the timeout.
#     BookReader loan status is always current.
loan_fulfillment_timeout_seconds = 60 * 5

# How long the auth token given to the BookReader should last.  After the auth token
# expires the BookReader will not be able to access the book.  The BookReader polls
# OL periodically to get fresh tokens.
BOOKREADER_AUTH_SECONDS = dateutil.MINUTE_SECS * 10
READER_AUTH_SECONDS = dateutil.MINUTE_SECS * 2

# Base URL for BookReader
try:
    bookreader_host = config.bookreader_host  # type: ignore[attr-defined]
except AttributeError:
    bookreader_host = "archive.org"

bookreader_stream_base = f"https://{bookreader_host}/stream"


# ######### Page Handlers


# Handler for /books/{bookid}/{title}/borrow
class checkout_with_ocaid(delegate.page):
    path = "/borrow/ia/(.*)"

    def GET(self, ocaid):
        """Redirect shim: Translate an IA identifier into an OL identifier and
        then redirects user to the canonical OL borrow page.
        """
        i = web.input()
        params = urllib.parse.urlencode(i)
        ia_edition = site.get().get("/books/ia:%s" % ocaid)
        if not ia_edition:
            raise web.notfound()
        edition = site.get().get(ia_edition.location)
        url = "%s/x/borrow" % edition.key
        raise web.seeother(url + "?" + params)

    def POST(self, ocaid):
        """Redirect shim: Translate an IA identifier into an OL identifier and
        then forwards a borrow request to the canonical borrow
        endpoint with this OL identifier.
        """
        ia_edition = site.get().get("/books/ia:%s" % ocaid)
        if not ia_edition:
            raise web.notfound()
        borrow().POST(ia_edition.location)


class BorrowParams(BaseModel):
    model_config = {"populate_by_name": True}

    action: Literal["borrow", "read", "locate", "return", "join-waitinglist", "leave-waitinglist", "browse"] = "borrow"
    format: str | None = None
    # web.input()/query param name is "_autoReadAloud" (matches the URL param
    # BookReader itself uses); aliased here so the Python-side name doesn't
    # start with an underscore.
    auto_read_aloud: str | None = Field(default=None, validation_alias="_autoReadAloud")
    q: str = ""
    redirect: str = ""

    @staticmethod
    def from_web_input(i) -> BorrowParams:
        return BorrowParams(
            action=i.action,
            format=i.format,
            auto_read_aloud=i._autoReadAloud,
            q=i.q,
            redirect=i.redirect,
        )


@dataclass
class BorrowRedirect:
    """A redirect outcome of handle_borrow_async(). The actual redirect, flash
    message, and cookie side effects are performed by whichever
    framework-specific caller invoked it (web.py or FastAPI), since those are
    done differently in each.
    """

    url: str
    permanent: bool = False  # False -> 303 See Other, True -> 301 Moved Permanently
    flash: tuple[str, str] | None = None  # (type, message), e.g. ("error", "...")
    clear_login_cookie: bool = False


@dataclass
class BorrowNotFound:
    pass


BorrowOutcome = BorrowRedirect | BorrowNotFound | str  # str = rendered interstitial HTML


async def handle_borrow_async(key: str, i: BorrowParams, *, s3_cookie: str | None, fastapi: bool = False) -> BorrowOutcome:  # noqa: PLR0912, PLR0915
    """Shared /borrow POST logic for both the web.py handler (via the
    handle_borrow sync bridge) and the FastAPI route (awaits directly).

    Returns an outcome object rather than performing the redirect/flash/
    cookie side effects itself, since those differ by framework -- except
    the interstitial render, which has no such side effect to bridge, so
    it's rendered directly here; `fastapi` tells it which framework this
    is, since it's the one thing this function can't otherwise infer.

    :param s3_cookie: Required, not read here: callers must read it on
        their own real thread before this may hop onto AsyncBridge's
        background thread, where web.ctx isn't populated.
    """
    action = i.action
    edition = site.get().get(key)
    if not edition:
        return BorrowNotFound()

    from openlibrary.book_providers import get_book_provider

    if action == "locate":
        return BorrowRedirect(edition.get_worldcat_url())

    # Direct to the first web book if at least one is available.
    if (
        action in ["borrow", "read"]
        and (provider := get_book_provider(edition))
        and provider.short_name != "ia"
        and (acquisitions := provider.get_acquisitions(edition))
        and acquisitions[0].access == "open-access"
    ):
        stats.increment("ol.loans.webbook")
        raw_name = acquisitions[0].provider_name or ""
        book_provider = Markup("<strong>") + escape(raw_name.replace("_", " ").title()) + Markup("</strong>") if raw_name else Markup("")
        return render_jinja_template(
            "interstitial.html.jinja",
            url=acquisitions[0].url,
            book_provider=book_provider,
            wait=5,
            fastapi=fastapi,
        )

    archive_url = get_bookreader_stream_url(edition.ocaid) + "?ref=ol"
    if i.auto_read_aloud is not None:
        archive_url += "&_autoReadAloud=show"

    if i.q:
        _q = urllib.parse.quote(i.q, safe="")
        return BorrowRedirect(archive_url + "#page/-/mode/2up/search/%s" % _q)

    # Make a call to availability v2 update the subjects according
    # to result if `open`, redirect to bookreader
    response = await lending.get_availability_async("identifier", [edition.ocaid])
    availability = response.get(edition.ocaid)
    if availability and availability["status"] == "open":
        from openlibrary.plugins.openlibrary.code import is_bot

        if not is_bot():
            stats.increment("ol.loans.openaccess")
        return BorrowRedirect(archive_url)

    error_redirect = archive_url

    # Strip scheme/host to prevent open-redirect attacks.
    if i.redirect:
        parsed = urllib.parse.urlsplit(i.redirect)
        edition_redirect = urllib.parse.urlunsplit(("", "", parsed.path, parsed.query, parsed.fragment))
    else:
        edition_redirect = edition.url()

    user = accounts.get_current_user()

    if user:
        account = OpenLibraryAccount.get_by_email(user.email)
        ia_itemname = account.itemname if account else None
        s3_keys = parse_s3_cookie(s3_cookie)
        lending.get_cached_loans_of_user.memcache_delete(user.key, {})  # invalidate cache for user loans
    if not user or not ia_itemname or not s3_keys:
        return_path = f"{edition_redirect}/borrow?action={action}"
        redirect_url = f"/account/login?redirect={urllib.parse.quote(return_path, safe='')}"
        if i.auto_read_aloud is not None:
            redirect_url += "&_autoReadAloud=" + i.auto_read_aloud
        return BorrowRedirect(redirect_url, clear_login_cookie=True)

    if action == "return":
        with contextlib.suppress(lending.PatronAccessException):
            await lending.s3_loan_api_async(s3_keys, ocaid=edition.ocaid, action="return_loan")

        edition.update_loan_status()
        user.update_loan_status()
        title = edition.title or _("this book")

        if user.has_borrowed(edition):
            flash = ("error", _("Unable to return %s. Please try again later or contact info@archive.org.") % title)
        else:
            stats.increment("ol.loans.return")
            flash = ("success", _("%s has been returned.") % title)
        return BorrowRedirect(edition_redirect, flash=flash)
    elif action == "join-waitinglist":
        lending.get_cached_user_waiting_loans.memcache_delete(user.key, {})  # invalidate cache for user waiting loans
        await lending.s3_loan_api_async(s3_keys, ocaid=edition.ocaid, action="join_waitlist")
        stats.increment("ol.loans.joinWaitlist")
        return BorrowRedirect(edition_redirect, permanent=True)
    elif action == "leave-waitinglist":
        lending.get_cached_user_waiting_loans.memcache_delete(user.key, {})  # invalidate cache for user waiting loans
        await lending.s3_loan_api_async(s3_keys, ocaid=edition.ocaid, action="leave_waitlist")
        stats.increment("ol.loans.leaveWaitlist")
        return BorrowRedirect(edition_redirect, permanent=True)

    elif action in ("borrow", "browse") and not user.has_borrowed(edition):
        borrow_access = await user_can_borrow_edition_async(user, edition)

        if not (s3_keys and borrow_access):
            stats.increment("ol.loans.outdatedAvailabilityStatus")
            return BorrowRedirect(error_redirect)

        try:
            await lending.s3_loan_api_async(s3_keys, ocaid=edition.ocaid, action="%s_book" % borrow_access)
            stats.increment("ol.loans.bookreader")
            stats.increment("ol.loans.%s" % borrow_access)
        except lending.PatronAccessException:
            stats.increment("ol.loans.blocked")
            return BorrowRedirect(
                key,
                flash=(
                    "error",
                    _("Your account has hit a lending limit. Please try again later or contact info@archive.org."),
                ),
            )

    if action in ("borrow", "browse", "read"):
        bookPath = "/stream/" + edition.ocaid
        if i.auto_read_aloud is not None:
            bookPath += "?_autoReadAloud=show"

        # Look for loans for this book
        user.update_loan_status()
        loans = lending.get_loans_of_user(user.key)
        for loan in loans:
            if loan["book"] == edition.key:
                return BorrowRedirect(
                    make_bookreader_auth_link(
                        loan["_key"],
                        edition.ocaid,
                        bookPath,
                        ia_userid=ia_itemname,
                    )
                )

    # Action not recognized
    return BorrowRedirect(error_redirect)


# Sync wrapper so web.py's borrow.POST (below) can call this without needing
# to be async itself; the FastAPI route awaits handle_borrow_async directly.
handle_borrow = async_bridge.wrap(handle_borrow_async)


# Handler for /books/{bookid}/{title}/borrow
class borrow(delegate.page):
    path = "(/books/.*)/borrow"

    def GET(self, key):
        return self.POST(key)

    def POST(self, key):
        """Called when the user wants to borrow the edition"""

        i = web.input(
            action="borrow",
            format=None,
            _autoReadAloud=None,
            q="",
            redirect="",
        )
        params = BorrowParams.from_web_input(i)
        s3_cookie = web.cookies().get("s3")
        result = handle_borrow(key, params, s3_cookie=s3_cookie)

        match result:
            case BorrowNotFound():
                raise web.notfound()
            case BorrowRedirect():
                if result.clear_login_cookie:
                    web.setcookie(config.login_cookie_name, "", expires=-1)
                if result.flash:
                    add_flash_message(*result.flash)
                raise (web.redirect if result.permanent else web.seeother)(result.url)
            case _:
                # The interstitial render_template() result, passed through as-is.
                return result


# Handler for /books/{bookid}/{title}/_borrow_status
class borrow_status(delegate.page):
    path = "(/books/.*)/_borrow_status"

    def GET(self, key):

        i = web.input(callback=None)

        edition = site.get().get(key)

        if not edition:
            raise web.notfound()

        edition.update_loan_status()
        available_formats = [loan["resource_type"] for loan in edition.get_available_loans()]
        loan_available = len(available_formats) > 0
        subjects = set()

        for work in edition.get("works", []):
            for subject in work.get_subjects():
                if subject in lending_subjects:
                    subjects.add(subject)

        output = {
            "id": key,
            "loan_available": loan_available,
            "available_formats": available_formats,
            "lending_subjects": list(subjects),
        }

        output_text = json.dumps(output)

        content_type = "application/json"
        if i.callback:
            content_type = "text/javascript"
            output_text = f"{i.callback} ( {output_text} );"

        return delegate.RawText(output_text, content_type=content_type)


class ia_loan_status(delegate.page):
    path = r"/ia_loan_status/(.*)"

    def GET(self, itemid):
        d = get_borrow_status(itemid)
        return delegate.RawText(json.dumps(d), content_type="application/json")


def get_borrow_status(itemid):
    """Returns borrow status for this IA identifier."""
    loan = lending.get_loan(itemid)
    has_loan = bool(loan)

    edition_keys = site.get().things({"type": "/type/edition", "ocaid": itemid})
    editions = site.get().get_many(edition_keys)
    has_waitinglist = editions and any(e.get_waitinglist_size() > 0 for e in editions)

    return web.storage(
        {
            "identifier": itemid,
            "checkedout": has_loan or has_waitinglist,
            "has_loan": has_loan,
            "has_waitinglist": has_waitinglist,
        }
    )


@public
def datetime_from_isoformat(expiry):
    """Returns datetime object, or None"""
    return None if expiry is None else parse_datetime(expiry)


@public
def datetime_from_utc_timestamp(seconds):
    return datetime.utcfromtimestamp(seconds)


def get_bookreader_stream_url(itemid: str) -> str:
    return bookreader_stream_base + "/" + itemid


# ######### Helper Functions


async def user_can_borrow_edition_async(user, edition) -> Literal["borrow", "browse", False]:
    """Returns the type of borrow for which patron is eligible, favoring
    "browse" over "borrow" where available, otherwise return False if
    patron is not eligible.

    """
    lending_st = await lending.get_groundtruth_availability_async(edition.ocaid, {})

    book_is_lendable = lending_st.get("is_lendable", False)
    book_is_waitlistable = lending_st.get("available_to_waitlist", False)
    user_is_below_loan_limit = user.get_loan_count() < user_max_loans

    if book_is_lendable:
        if req_context.get().print_disabled:
            return "borrow"
        elif user_is_below_loan_limit:
            if lending_st.get("available_to_browse"):
                return "browse"
            elif lending_st.get("available_to_borrow") or (book_is_waitlistable and is_users_turn_to_borrow(user, edition)):
                return "borrow"
    return False


def is_users_turn_to_borrow(user, edition) -> bool:
    """If this user is waiting on this edition, it can only borrowed if
    user is the user is the first in the waiting list.
    """
    waiting_loan = user.get_waiting_loan_for(edition.ocaid)
    return waiting_loan and waiting_loan["status"] == "available" and waiting_loan["position"] == 1


def is_admin() -> bool:
    """Returns True if the current user is in admin usergroup."""
    user = accounts.get_current_user()
    return user is not None and user.key in [m.key for m in site.get().get("/usergroup/admin").members]


def ia_hash(token_data: str) -> str:
    try:
        access_key = config.ia_access_secret.encode("utf-8")  # type: ignore[attr-defined]
    except AttributeError:
        raise RuntimeError("config value config.ia_access_secret is not present -- check your config")
    return hmac.new(access_key, token_data.encode("utf-8"), hashlib.md5).hexdigest()


def make_ia_token(item_id: str, expiry_seconds: int) -> str:
    """Make a key that allows a client to access the item on archive.org for the number of
    seconds from now.
    """
    # $timestamp = $time+600; //access granted for ten minutes
    # $hmac = hash_hmac('md5', "{$id}-{$timestamp}", configGetValue('ol-loan-secret'));
    # return "{$timestamp}-{$hmac}";

    timestamp = int(time.time() + expiry_seconds)
    token_data = "%s-%d" % (item_id, timestamp)
    token = "%d-%s" % (timestamp, ia_hash(token_data))
    return token


def make_bookreader_auth_link(loan_key, item_id, book_path, ia_userid=None) -> str:
    """
    Generate a link to BookReaderAuth.php that starts the BookReader
    with the information to initiate reading a borrowed book
    """
    auth_link = "https://%s/bookreader/BookReaderAuth.php?" % bookreader_host
    params = {
        "uuid": loan_key,
        "token": make_ia_token(item_id, BOOKREADER_AUTH_SECONDS),
        "id": item_id,
        "bookPath": book_path,
        "iaUserId": ia_userid,
        "iaAuthToken": make_ia_token(ia_userid, READER_AUTH_SECONDS),
    }
    return auth_link + urllib.parse.urlencode(params)


lending.setup(config)
vendors.setup(config)
