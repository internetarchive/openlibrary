"""Upstream customizations."""

import datetime
import functools
import hashlib
import json
import os.path
import random
import re
from dataclasses import dataclass
from typing import Any

import web

from infogami import config
from infogami.core import code as core
from infogami.infobase import client
from infogami.plugins.api.code import jsonapi, make_query
from infogami.plugins.api.code import request as infogami_request
from infogami.utils import delegate
from infogami.utils.context import context
from infogami.utils.view import (
    public,
    render,
    render_template,  # used for its side effects
    safeint,
)
from openlibrary import accounts  # noqa: F401 side effects may be needed
from openlibrary.core import lending
from openlibrary.plugins.upstream import (
    addbook,
    addtag,
    borrow,  # noqa: F401 side effects may be needed
    checkins,
    covers,
    edits,
    likes,  # noqa: F401 side effects may be needed
    merge_authors,
    models,
    recentchanges,  # noqa: F401 side effects may be needed
    spamcheck,
    utils,
    yearly_reading_goals,
)  # TODO: unused imports?
from openlibrary.plugins.upstream.utils import render_component

if not config.get("coverstore_url"):
    config.coverstore_url = "https://covers.openlibrary.org"  # type: ignore[attr-defined]

import logging

logger = logging.getLogger("openlibrary.plugins.upstream.code")


class history(delegate.mode):
    """Overwrite ?m=history to remove IP"""

    encoding = "json"

    @jsonapi
    def GET(self, path):
        query = make_query(web.input(), required_keys=["author", "offset", "limit"])
        query["key"] = path
        query["sort"] = "-created"
        # Possibly use infogami.plugins.upstream.utils get_changes to avoid json load/dump?
        history = json.loads(infogami_request("/versions", data={"query": json.dumps(query)}))
        for _, row in enumerate(history):
            row.pop("ip")
        return json.dumps(history)


class edit(core.edit):
    """Overwrite ?m=edit behaviour for author, book, work, and people pages."""

    def GET(self, key):
        page = web.ctx.site.get(key)
        editable_keys_re = re.compile(r"/(authors|books|works|tags|lists|series|people/[^/]+/lists)/OL.*")
        if editable_keys_re.match(key):
            if page is None:
                return web.seeother(key)
            else:
                return addbook.safe_seeother(page.url(suffix="/edit"))
        else:
            return core.edit.GET(self, key)

    def POST(self, key):
        if re.compile("/(people/[^/]+)").match(key) and spamcheck.is_spam():
            return render_template("message.html", "Oops", "Something went wrong. Please try again later.")
        return core.edit.POST(self, key)


class view(core.view):
    """Prepare lending/availability in Python for /works and /books HTML views.

    Other types and modes/encodings continue through their existing handlers.
    """

    def GET(self, path):
        # Everything else goes through core.view unchanged, without the
        # redundant get_version() load below.
        if not path.startswith(("/works/", "/books/")):
            return core.view.GET(self, path)

        i = web.input(v=None)
        if i.v is not None and safeint(i.v, None) is None:
            raise web.seeother(web.changequery(v=None))

        p = core.db.get_version(path, i.v)
        if p is None or p.type.key not in ("/type/work", "/type/edition"):
            return core.view.GET(self, path)

        # context.user avoids a second, non-memoized get_user() round-trip.
        try:
            book_page_context = prepare_book_page(p, i, context.user)
        except Exception:
            logger.exception("prepare_book_page failed for %r; falling back to core.view", path)
            return core.view.GET(self, path)
        return render.viewpage(p, book_page_context)


# handlers for change photo and change cover


class change_cover(delegate.mode):
    path = r"(/books/OL\d+M)/cover"

    def GET(self, key):
        page = web.ctx.site.get(key)
        if page is None or page.type.key not in ["/type/edition", "/type/author"]:
            raise web.seeother(key)
        return render.change_cover(page)


class change_photo(change_cover):
    path = r"(/authors/OL\d+A)/photo"


del delegate.modes["change_cover"]  # delete change_cover mode added by openlibrary plugin


class components_test(delegate.page):
    path = "/_dev/components/HelloWorld"

    def GET(self):
        return render_component("HelloWorld") + render_component("HelloWorld")


class library_explorer(delegate.page):
    path = "/explore"

    def GET(self):
        return render_template("library_explorer")


class merge_work(delegate.page):
    path = "/works/merge"

    def GET(self):
        i = web.input(records="", mrid=None, primary=None)
        user = web.ctx.site.get_user()

        if user is None:
            raise web.unauthorized()
        has_access = user and user.is_librarian_or_higher()
        if not has_access:
            raise web.forbidden()

        optional_kwargs = {}
        if not user.is_super_librarian_or_higher():
            optional_kwargs["can_merge"] = "false"

        return render_template("merge/works", mrid=i.mrid, primary=i.primary, **optional_kwargs)


@functools.cache
@public
def static_url(path):
    """Takes path relative to static/ and constructs url to that resource with hash."""
    pardir = os.path.pardir
    fullpath = os.path.abspath(os.path.join(__file__, pardir, pardir, pardir, pardir, "static", path))
    with open(fullpath, "rb") as in_file:
        digest = hashlib.md5(in_file.read()).hexdigest()
    return f"/static/{path}?v={digest}"


class DynamicDocument:
    """Dynamic document is created by concatenating various rawtext documents in the DB.
    Used to generate combined js/css using multiple js/css files in the system.
    """

    def __init__(self, root):
        self.root = root.removesuffix("/")
        self.docs = None
        self._text = None
        self.last_modified = None

    def update(self):
        keys = web.ctx.site.things({"type": "/type/rawtext", "key~": self.root + "/*"})
        docs = sorted(web.ctx.site.get_many(keys), key=lambda doc: doc.key)
        if docs:
            self.last_modified = min(doc.last_modified for doc in docs)
            self._text = "\n\n".join(doc.get("body", "") for doc in docs)
        else:
            self.last_modified = datetime.datetime.utcnow()
            self._text = ""

    def get_text(self):
        """Returns text of the combined documents"""
        if self._text is None:
            self.update()
        return self._text

    def md5(self):
        """Returns md5 checksum of the combined documents"""
        return hashlib.md5(self.get_text().encode("utf-8")).hexdigest()


def create_dynamic_document(url, prefix):
    """Creates a handler for `url` for servering combined js/css for `prefix/*` pages"""
    doc = DynamicDocument(prefix)

    if url.endswith(".js"):
        content_type = "text/javascript"
    elif url.endswith(".css"):
        content_type = "text/css"
    else:
        content_type = "text/plain"

    class page(delegate.page):
        """Handler for serving the combined content."""

        path = "__registered_later_without_using_this__"

        def GET(self):
            i = web.input(v=None)
            v = doc.md5()
            if v != i.v:
                raise web.seeother(web.changequery(v=v))

            if web.modified(etag=v):
                oneyear = 365 * 24 * 3600
                web.header("Content-Type", content_type)
                web.header("Cache-Control", "Public, max-age=%d" % oneyear)
                web.lastmodified(doc.last_modified)
                web.expires(oneyear)
                return delegate.RawText(doc.get_text())

        def url(self):
            return url + "?v=" + doc.md5()

        def reload(self):
            doc.update()

    class hook(client.hook):
        """Hook to update the DynamicDocument when any of the source pages is updated."""

        def on_new_version(self, page):
            if page.key.startswith(doc.root):
                doc.update()

    # register the special page
    delegate.pages[url] = {}
    delegate.pages[url][None] = page
    return page


all_js = create_dynamic_document("/js/all.js", config.get("js_root", "/js"))
web.template.Template.globals["all_js"] = all_js()

all_css = create_dynamic_document("/css/all.css", config.get("css_root", "/css"))
web.template.Template.globals["all_css"] = all_css()


def reload():
    """Reload all.css and all.js"""
    all_css().reload()
    all_js().reload()


@public
def get_document(key, limit_redirs=5):
    doc = None
    for i in range(limit_redirs):
        doc = web.ctx.site.get(key)
        if doc is None:
            return None
        if doc.type.key == "/type/redirect":
            key = doc.location
        else:
            return doc
    return doc


@dataclass
class BookPageContext:
    """Data needed to render a /works or /books page, prepared in Python
    before the template renders so that no lending/availability I/O
    (including the ground-truth availability fallback) happens from
    inside a template.
    """

    work: Any
    edition: Any
    editions: list
    editions_limit: int | None
    previews: list
    show_observations: bool
    lending_state: str


def _resolve_work(page):
    """Return the work for a /works or /books page, and whether to show
    reader observations (hidden for editions without a real work)."""
    if page.key.startswith("/works"):
        return page, True
    if page.works:
        return next(iter(page.works)), True
    return page.make_work_from_orphaned_edition(), False


def _resolve_edition_request(page, query_params):
    """Resolve the edition explicitly requested via `?edition=key:`, the
    edition itself on /books pages, or a provider/id pair for `provider:id`.

    Returns (requested_edition, provider, selected_id); requested_edition is
    None when the caller should fall back to picking the best edition.
    """
    if query_params.get("edition", "").startswith("key:"):
        return core.db.get_type(query_params.get("edition").split(":")[1]), None, None
    if page.key.startswith("/books"):
        # We are on an editions page: an edition has been explicitly selected
        return page, None, None
    if query_params.get("edition"):
        from openlibrary.book_providers import get_book_provider_by_name

        if ":" in query_params.get("edition"):
            provider_name, selected_id = query_params.get("edition").split(":", 1)
        else:
            provider_name, selected_id = "ia", query_params.get("edition")
        return None, get_book_provider_by_name(provider_name), selected_id
    return None, None, None


def _fetch_editions(work, requested, provider, selected_id, mode):
    """Fetch a work's editions, applying the ebooks-only / edition-limit rules.

    Book availability of the fetched editions is injected by the bulk
    get_availability API inside get_sorted_editions().
    """
    edition_count = work.edition_count if work and work.edition_count else 1
    ebooks_only = (mode == "ebooks") or (mode != "all" and edition_count > 10)

    # For performance reasons, limit to 10 ebooks.
    # Tradeoff: limits our ability to select best edition.
    editions_limit = None if mode in ("all", "ebooks") else 10
    # keys ensures the current edition we're on or requested edition are fetched by get_sorted_editions
    if requested:
        keys = [requested.key]
    elif provider:
        # provider is only ever set alongside selected_id, above.
        assert selected_id is not None
        keys = provider.get_olids(selected_id)
    else:
        keys = None

    editions = []
    if ebooks_only:
        editions = work.get_sorted_editions(ebooks_only=ebooks_only, limit=editions_limit, keys=keys)
    if not editions:
        editions = work.get_sorted_editions(limit=editions_limit, keys=keys)
    return editions, editions_limit


def _select_edition(editions, requested, provider, selected_id, page):
    """Pick the edition to render: the explicitly requested one, the one
    matching a requested provider/id, else the default best edition."""
    if not editions:
        return requested or page, provider
    if requested:
        return requested, provider
    if provider:
        return next((e for e in editions if selected_id in provider.get_identifiers(e)), editions[0]), provider
    from openlibrary.book_providers import get_best_edition

    return get_best_edition(editions)


def _attach_availability(edition, availabilities):
    """Seed the selected edition's availability from the bulk map, falling
    back to the ground-truth API for that edition only when bulk errored
    (the one outbound call left on book pages)."""
    if not edition.get("availability"):
        edition["availability"] = (edition.get("ocaid") and availabilities.get(edition["ocaid"])) or {}

    ocaid = edition.get("ocaid")
    if edition.get("availability", {}).get("status") == "error" and ocaid:
        try:
            if gt := lending.get_cached_groundtruth_availability(ocaid):
                # Copy, not mutate: the bulk dict may be shared with availabilities/editions
                edition["availability"] = {**edition["availability"], **gt}
        except Exception:
            # Unlike the old template-side call (caught by Templetor's
            # saferender()), an uncaught exception here would 500 the whole
            # page. Keep the bulk ("error") availability instead.
            logger.exception("get_cached_groundtruth_availability(%r) failed; keeping bulk availability", ocaid)


def prepare_book_page(page, query_params, user=None) -> BookPageContext:
    """Resolves the work, selected edition, and lending state for a /works
    or /books page. Ported from type/edition/view.html so that no
    lending/availability I/O (including the ground-truth fallback) happens
    from inside a template.

    :param page: the Work or Edition already loaded for this request.
    :param query_params: a mapping supporting `.get(name, default)`, e.g. `web.input()`.
    :param user: the logged-in user, if any (only used to gate loan/waitlist checks).
    """
    work, show_observations = _resolve_work(page)

    # This can happen when looking at past versions of an edition whose
    # work has since been merged.
    if work.type.key == "/type/redirect":
        redir = work
        if (fetched := get_document(redir.key)) is not None:
            work = fetched
        else:
            logger.warning("get_document(%r) returned None for redirect %r", redir.key, page.key)
        work["title"] = "↪ " + redir.key

    requested, provider, selected_id = _resolve_edition_request(page, query_params)
    editions, editions_limit = _fetch_editions(work, requested, provider, selected_id, query_params.get("mode"))
    availabilities = {e.availability.get("identifier"): e.availability for e in editions}

    previews = [e for e in editions if e.get("ocaid")]

    edition, provider = _select_edition(editions, requested, provider, selected_id, page)
    _attach_availability(edition, availabilities)

    lending_state = lending.get_lending_state(
        edition or work,
        user=user,
        check_loan_status=bool(user),
    )

    return BookPageContext(
        work=work,
        edition=edition,
        editions=editions,
        editions_limit=editions_limit,
        previews=previews,
        show_observations=show_observations,
        lending_state=lending_state,
    )


class revert(delegate.mode):
    def GET(self, key):
        raise web.seeother(web.changequery(m=None))

    def POST(self, key):
        i = web.input("v", _comment=None)
        v = i.v and safeint(i.v, None)

        if v is None:
            raise web.seeother(web.changequery({}))

        user = web.ctx.site.get_user()
        if not web.ctx.site.can_write(key) or not (user and user.is_super_librarian_or_higher()):
            return render.permission_denied(web.ctx.fullpath, "Permission denied to edit " + key + ".")

        thing = web.ctx.site.get(key, i.v)

        if not thing:
            raise web.notfound()

        def revert(thing):
            if thing.type.key == "/type/delete" and thing.revision > 1:
                prev = web.ctx.site.get(thing.key, thing.revision - 1)
                if prev.type.key in ["/type/delete", "/type/redirect"]:
                    return revert(prev)
                else:
                    prev._save("revert to revision %d" % prev.revision, action="revert-version")
                    return prev
            elif thing.type.key == "/type/redirect":
                redirect = web.ctx.site.get(thing.location)
                if redirect and redirect.type.key not in [
                    "/type/delete",
                    "/type/redirect",
                ]:
                    return redirect
                else:
                    # bad redirect. Try the previous revision
                    prev = web.ctx.site.get(thing.key, thing.revision - 1)
                    return revert(prev)
            else:
                return thing

        def process(value):
            if isinstance(value, list):
                return [process(v) for v in value]
            elif isinstance(value, client.Thing):
                if value.key:
                    if value.type.key in ["/type/delete", "/type/revert"]:
                        return revert(value)
                    else:
                        return value
                else:
                    for k in value:
                        value[k] = process(value[k])
                    return value
            else:
                return value

        for k in thing:
            thing[k] = process(thing[k])

        comment = i._comment or "reverted to revision %d" % v
        thing._save(comment, action="revert-version")
        raise web.seeother(key)


def setup():
    """Setup for upstream plugin"""
    models.setup()
    utils.setup()
    addbook.setup()
    addtag.setup()
    covers.setup()
    merge_authors.setup()
    # merge_works.setup() # ILE code
    edits.setup()
    checkins.setup()
    yearly_reading_goals.setup()

    from openlibrary.plugins.upstream import data, jsdef

    data.setup()

    # setup template globals
    from openlibrary.i18n import ugettext, ungettext

    web.template.Template.globals.update(
        {
            "_": ugettext,
            "ungettext": ungettext,
            "random": random.Random(),
            "commify": web.commify,
            "group": web.group,
            "storage": web.storage,
            "all": all,
            "any": any,
            "locals": locals,
        }
    )

    web.template.STATEMENT_NODES["jsdef"] = jsdef.JSDefNode


setup()
