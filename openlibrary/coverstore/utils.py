"""Utilities for coverstore"""

import contextlib
import functools
import json
import mimetypes
import os
import random
import re
import string
import traceback
from io import IOBase as file
from typing import Final
from urllib.parse import parse_qsl, unquote, unquote_plus, urlsplit, urlunsplit  # type: ignore[attr-defined]
from urllib.parse import urlencode as real_urlencode

import httpx

from openlibrary.utils.async_utils import cache_per_event_loop

COVERSTORE_USER_AGENT = "Mozilla/5.0 (Compatible; coverstore downloader http://covers.openlibrary.org)"
# Note: These domains need to also be kept insync with the IA squid proxy
ALLOWED_COVER_URLS: Final = (
    # e.g. https://archive.org/download/goody/page/title.jpg
    # e.g. https://archive.org/download/goody/page/cover_w500_h500.jpg
    r"^https?://archive.org/download/[^?#]+/page/(cover|title)(_w\d+)?(_h\d+)?(\.jpg)?$",
    # e.g. https://archive.org/services/img/goody/full/pct:600/0/default.jpg
    r"^https?://archive.org/services/img/[^?#]+/full/pct:\d+/0/(default)\.jpg$",
    # e.g. https://covers.openlibrary.org/b/id/15082914-M.jpg
    r"^https?://covers.openlibrary.org/b/[^/?#]+/[^/?#.]+(-[A-Z])?\.jpg$",
    r"^https?://books.google.com/.*$",
    r"^https?://commons.wikimedia.org/.*$",
    r"^https?://m.media-amazon.com/.*$",
    # e.g. https://www.gutenberg.org/cache/epub/1661/pg1661.cover.small.jpg
    r"^https?://www\.gutenberg\.org/cache/[^?#]+$",
    # e.g. https://cdn.sanity.io/images/3lm68n5v/production/e7ffe418212f76c942fe906ae66cff17867bd602-190x300.jpg?w=1920&q=75&auto=format
    r"^https?://cdn\.sanity\.io/images/[^#]+$",
)


# Per event loop, not process-wide: an AsyncClient binds its pooled connections to
# whichever loop first contends for them. See cache_per_event_loop.
get_async_session = cache_per_event_loop(
    functools.partial(
        httpx.AsyncClient,
        headers={"User-Agent": COVERSTORE_USER_AGENT},
        timeout=10,
        follow_redirects=True,
    )
)


def is_allowed_cover_url(url: str) -> bool:
    return any(re.match(pattern, url) for pattern in ALLOWED_COVER_URLS)


# Open Library / Internet Archive hosts a coverstore response may redirect a
# browser to. Host-anchored (an exact host or a subdomain of one), never a
# substring, so both https://openlibrary.org.evil.com/ and
# https://evil.com/?x=openlibrary.org are rejected.
TRUSTED_REDIRECT_HOSTS: Final = frozenset(
    {
        "openlibrary.org",
        "covers.openlibrary.org",
        "archive.org",
    }
)


def _host_is_trusted(host: str | None) -> bool:
    if not host:
        return False
    host = host.lower()
    return any(host == h or host.endswith("." + h) for h in TRUSTED_REDIRECT_HOSTS)


def is_allowed_default_redirect_url(url: str) -> bool:
    """True if ``url`` is safe to 303-redirect a browser to as a missing-cover
    fallback (the ``?default=<url>`` query param): an http(s) URL on a trusted
    OL/IA host, or an already-allowed external cover URL. Everything else
    (evil.com, internal hosts, scheme-relative ``//evil.com``, ``javascript:``)
    is rejected, closing the GHSA-8ffj open redirect."""
    # A backslash has no place in a URL, but WHATWG browsers normalise it to "/"
    # while urlsplit does not: https://evil.com\@openlibrary.org parses here as
    # host=openlibrary.org (trusted) yet a browser navigates to evil.com. Reject
    # it outright so the string we validate matches the string the browser uses.
    if "\\" in url:
        return False
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    return _host_is_trusted(parts.hostname) or is_allowed_cover_url(url)


def safe_redirect_target(target: str | None, fallback: str = "/") -> str:
    """Return ``target`` only when it is a safe redirect destination, else
    ``fallback``. Safe means a site-relative path (``/foo``, but not ``//evil``
    or ``/\\evil``) or an absolute http(s) URL on a trusted OL/IA host. This
    neutralises the attacker-controlled redirect_url/success_url/failure_url/
    referer open redirects on the touch/delete/upload endpoints."""
    if not target:
        return fallback
    cleaned = target.strip()
    # Browsers strip embedded control chars; a value carrying them is hostile.
    if not cleaned or any(c in cleaned for c in ("\n", "\r", "\t")):
        return fallback
    # A backslash anywhere is unsafe: WHATWG browsers normalise "\" to "/", so
    # urlsplit's view of the host would differ from the browser's (e.g.
    # https://evil.com\@openlibrary.org parses as host=openlibrary.org here but
    # navigates to evil.com). Reject it rather than validate a different string.
    if "\\" in cleaned:
        return fallback
    # Scheme-relative host -> unsafe.
    if cleaned.startswith("//"):
        return fallback
    try:
        parts = urlsplit(cleaned)
    except ValueError:
        return fallback
    # Pure site-relative path (no scheme, no netloc).
    if not parts.scheme and not parts.netloc:
        return cleaned if cleaned.startswith("/") else fallback
    # Absolute URL: only http(s) on a trusted host.
    if parts.scheme in ("http", "https") and _host_is_trusted(parts.hostname):
        return cleaned
    return fallback


def safeint(value, default=None):
    """
    >>> safeint('1')
    1
    >>> safeint('x')
    >>> safeint('x', 0)
    0
    """
    try:
        return int(value)
    except TypeError, ValueError:
        return default


def get_ol_url():
    # Import here to avoid top-level import with side-effects (requires config being loaded)
    from openlibrary.coverstore import config

    return config.ol_url.removesuffix("/")


async def ol_things(key: str, value: str) -> list[str]:
    # Import here to avoid top-level import with side-effects (requires config being loaded)
    from openlibrary.coverstore import oldb

    if oldb.is_supported():
        return oldb.query(key, value)

    query = {
        "type": "/type/edition",
        key: value,
        "sort": "last_modified",
        "limit": 10,
    }
    try:
        resp = await get_async_session().get(
            f"{get_ol_url()}/api/things",
            params={"query": json.dumps(query)},
        )
        result = resp.json()
        return result["result"]
    except httpx.RequestError:
        traceback.print_exc()
        return []


async def ol_get(olkey: str) -> dict | None:
    # Import here to avoid top-level import with side-effects (requires config being loaded)
    from openlibrary.coverstore import oldb

    if oldb.is_supported():
        return oldb.get(olkey)

    try:
        resp = await get_async_session().get(f"{get_ol_url()}/{olkey}.json")
        return resp.json()
    except httpx.RequestError:
        return None


class DisallowedCoverUrl(Exception):
    pass


async def download_external_image(url: str) -> bytes:
    if not is_allowed_cover_url(url):
        raise DisallowedCoverUrl(f"URL {url} is not an allowed cover URL")

    resp = await get_async_session().get(url)
    return resp.content


def urldecode(url: str) -> tuple[str, dict[str, str]]:
    """
    >>> urldecode('http://google.com/search?q=bar&x=y')
    ('http://google.com/search', {'q': 'bar', 'x': 'y'})
    >>> urldecode('http://google.com/')
    ('http://google.com/', {})
    """
    split_url = urlsplit(url)
    items = parse_qsl(split_url.query)
    d = {unquote(k): unquote_plus(v) for (k, v) in items}
    base = urlunsplit(split_url._replace(query=""))
    return base, d


def changequery(url, **kw):
    """
    >>> changequery('http://google.com/search?q=foo', q='bar', x='y')
    'http://google.com/search?q=bar&x=y'
    """
    base, params = urldecode(url)
    params.update(kw)
    return base + "?" + real_urlencode(params)


def read_file(path, offset, size, chunk=50 * 1024):
    """Returns an iterator over file data at specified offset and size.

    >>> len(b"".join(read_file('/dev/urandom', 100, 10000)))
    10000
    """
    with open(path, "rb") as f:
        f.seek(offset)
        while size:
            data = f.read(min(chunk, size))
            size -= len(data)
            if data:
                yield data
            else:
                raise OSError("file truncated")


def rm_f(filename):
    with contextlib.suppress(OSError):
        os.remove(filename)


chars = string.ascii_letters + string.digits


def random_string(n):
    return "".join([random.choice(chars) for i in range(n)])


def urlencode(data):
    """
    urlencodes the given data dictionary. If any of the value is a file object, data is multipart encoded.

    @@@ should go into web.browser
    """
    multipart = False
    for v in data.values():
        if isinstance(v, file):
            multipart = True
            break

    if not multipart:
        return "application/x-www-form-urlencoded", real_urlencode(data)
    else:
        # adopted from http://code.activestate.com/recipes/146306/
        def get_content_type(filename):
            return mimetypes.guess_type(filename)[0] or "application/octet-stream"

        def encode(key, value, out):
            if isinstance(value, file):
                out.append("--" + BOUNDARY)
                out.append(f'Content-Disposition: form-data; name="{key}"; filename="{value.name}"')
                out.append(f"Content-Type: {get_content_type(value.name)}")
                out.append("")
                out.append(value.read())
            elif isinstance(value, list):
                for v in value:
                    encode(key, v)
            else:
                out.append("--" + BOUNDARY)
                out.append(f'Content-Disposition: form-data; name="{key}"')
                out.append("")
                out.append(value)

        BOUNDARY = "----------ThIs_Is_tHe_bouNdaRY_$"
        CRLF = "\r\n"
        out = []
        for k, v in data.items():
            encode(k, v, out)
        body = CRLF.join(out)
        content_type = f"multipart/form-data; boundary={BOUNDARY}"
        return content_type, body


if __name__ == "__main__":
    import doctest

    doctest.testmod()
