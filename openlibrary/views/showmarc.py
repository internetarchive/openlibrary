"""
Hook to show MARC or other source record details in Open Library.
"""

import re
from base64 import b64decode, b64encode
from contextlib import suppress

import requests
import web

from .. import app
from ..core import cache
from ..utils import dateutil


class old_show_marc(app.view):
    path = "/show-marc/(.*)"

    def GET(self, param):
        raise web.seeother("/show-records/" + param)


class show_ia(app.view):
    path = "/show-records/ia:(.*)"

    def GET(self, ia):
        error_404 = False
        url = f"https://archive.org/download/{ia}/{ia}_meta.mrc"
        try:
            response = requests.get(url, timeout=3)
            response.raise_for_status()
            data = response.content
        except requests.Timeout:
            return "ERROR: archive.org timed out"
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                error_404 = True
            else:
                return "ERROR:" + str(e)

        if error_404:  # no MARC record
            url = f"https://archive.org/download/{ia}/{ia}_meta.xml"
            try:
                response = requests.get(url, timeout=3)
                response.raise_for_status()
                data = response.content
            except requests.Timeout:
                return "ERROR: archive.org timed out"
            except requests.HTTPError as e:
                return "ERROR:" + str(e)
            raise web.seeother("https://archive.org/details/" + ia)

        books = web.ctx.site.things(
            {
                "type": "/type/edition",
                "source_records": "ia:" + ia,
            }
        ) or web.ctx.site.things(
            {
                "type": "/type/edition",
                "ocaid": ia,
            }
        )

        from openlibrary.catalog.marc import html

        try:
            leader_len = int(data[:5])
        except ValueError:
            return "ERROR reading MARC for " + ia

        if len(data) != leader_len:
            data = data.decode("utf-8").encode("raw_unicode_escape")
        assert len(data) == int(data[:5])

        try:
            record = html.html_record(data)
        except ValueError:
            record = None

        # Precompute the edition document for the breadcrumb
        edition = books[0] if books else None
        if edition:
            edition = web.ctx.site.get(edition)

        return app.render_template("showia", ia, record, edition=edition)


class show_amazon(app.view):
    path = "/show-records/amazon:(.*)"

    def GET(self, asin):
        return app.render_template("showamazon", asin)


class show_bwb(app.view):
    path = "/show-records/bwb:(.*)"

    def GET(self, isbn):
        return app.render_template("showbwb", isbn)


class show_google_books(app.view):
    path = "/show-records/google_books:(.*)"

    def GET(self, isbn):
        return app.render_template("showgoogle_books", isbn)


re_bad_meta_mrc = re.compile(r"^([^/]+)_meta\.mrc$")

# MARC dumps are static: a fetched record stays valid for weeks. Caching
# turns repeat views (and retries after a timeout) into cache hits instead
# of another 4-8s round trip to archive.org (#13874).
MARC_CACHE_TTL = 30 * dateutil.DAY_SECS


def _marc_cache_key(filename, offset, length):
    return "marc:%s:%d:%d" % (filename, offset, length)


def _fetch_marc_range(filename, offset, length):
    """Fetch record bytes from archive.org. Raises on timeout/HTTP error."""
    r0, r1 = offset, offset + 100000
    url = "https://archive.org/download/%s" % filename
    headers = {"Range": "bytes=%d-%d" % (r0, r1)}
    response = requests.get(url, headers=headers, timeout=3)
    response.raise_for_status()
    return response.content[:100000]


def _cached_marc_record(filename, offset, length):
    """Record bytes, from memcache when present (base64: memcache is JSON).

    Returns None only when there is no cached copy and the live fetch
    fails; callers keep the previous timeout/HTTP error behavior then.
    Raises requests.Timeout / requests.HTTPError on a live-fetch failure
    with an empty cache, exactly as before.
    """
    key = _marc_cache_key(filename, offset, length)
    try:
        cached = cache.get_memcache().get(key)
    except Exception:  # noqa: BLE001 — cache must never break the view
        cached = None
    if cached is not None:
        return b64decode(cached)
    result = _fetch_marc_range(filename, offset, length)
    with suppress(Exception):
        cache.get_memcache().set(key, b64encode(result).decode("ascii"), expires=MARC_CACHE_TTL)
    return result


class show_marc(app.view):
    path = r"/show-records/(.*):(\d+):(\d+)"

    def GET(self, filename, offset, length):
        if m := re_bad_meta_mrc.match(filename):
            raise web.seeother("/show-records/ia:" + m.group(1))

        loc = f"marc:{filename}:{offset}:{length}"

        books = web.ctx.site.things(
            {
                "type": "/type/edition",
                "source_records": loc,
            }
        )

        offset = int(offset)
        length = int(length)

        try:
            result = _cached_marc_record(filename, offset, length)
        except requests.Timeout:
            return "ERROR: archive.org timed out"
        except requests.HTTPError as e:
            return "ERROR:" + str(e)

        if (len_in_rec := int(result[:5])) != length:
            raise web.seeother("/show-records/%s:%d:%d" % (filename, offset, len_in_rec))

        from openlibrary.catalog.marc import html

        try:
            record = html.html_record(result[0:length])
        except ValueError:
            record = None

        # Precompute the edition document for the breadcrumb
        edition = books[0] if books else None
        if edition:
            edition = web.ctx.site.get(edition)

        return app.render_template("showmarc", record, filename, offset, length, edition=edition)
