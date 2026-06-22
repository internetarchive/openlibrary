"""Utilities for coverstore"""

from __future__ import annotations

import contextlib
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

import requests

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
)


session = requests.Session()
session.headers.update({"User-Agent": COVERSTORE_USER_AGENT})


def is_allowed_cover_url(url: str) -> bool:
    return any(re.match(pattern, url) for pattern in ALLOWED_COVER_URLS)


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
    except (TypeError, ValueError):
        return default


def get_ol_url():
    # Import here to avoid top-level import with side-effects (requires config being loaded)
    from openlibrary.coverstore import config

    return config.ol_url.removesuffix("/")


def ol_things(key: str, value: str) -> list[str]:
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
        resp = session.get(
            f"{get_ol_url()}/api/things",
            params={"query": json.dumps(query)},
            timeout=10,
        )
        result = resp.json()
        return result["result"]
    except OSError:
        traceback.print_exc()
        return []


def ol_get(olkey: str) -> dict | None:
    # Import here to avoid top-level import with side-effects (requires config being loaded)
    from openlibrary.coverstore import oldb

    if oldb.is_supported():
        return oldb.get(olkey)

    try:
        return session.get(f"{get_ol_url()}/{olkey}.json", timeout=10).json()
    except OSError:
        return None


class DisallowedCoverUrl(Exception):
    pass


def download_external_image(url: str) -> bytes:
    if not is_allowed_cover_url(url):
        raise DisallowedCoverUrl(f"URL {url} is not an allowed cover URL")

    return session.get(url, timeout=10).content


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
