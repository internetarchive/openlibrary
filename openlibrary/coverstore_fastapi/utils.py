"""Small helpers shared across the FastAPI coverstore."""

import datetime
import random
import re
import string
import time
import urllib.parse
from typing import Any, Final

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


def safeint(value, default=None):
    """Same semantics as openlibrary.coverstore.utils.safeint."""
    try:
        return int(value)
    except TypeError, ValueError:
        return default


def is_allowed_cover_url(url: str) -> bool:
    return any(re.match(pattern, url) for pattern in ALLOWED_COVER_URLS)


class DisallowedCoverUrl(Exception):
    pass


def utcnow() -> datetime.datetime:
    """Naive UTC now (the legacy coverstore stores naive UTC timestamps)."""
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


def httpdate(date: datetime.datetime) -> str:
    """Formats a naive UTC datetime as an HTTP date (same as web.net.httpdate)."""
    return date.strftime("%a, %d %b %Y %H:%M:%S GMT")


def parse_httpdate(value: str) -> datetime.datetime | None:
    """Parses an HTTP date (same as web.net.parsehttpdate), returning None on failure."""
    try:
        t = time.strptime(value, "%a, %d %b %Y %H:%M:%S GMT")
    except ValueError:
        return None
    return datetime.datetime(*t[:6])


chars = string.ascii_letters + string.digits


def random_string(n: int) -> str:
    return "".join([random.choice(chars) for _ in range(n)])


def urldecode(url: str) -> tuple[str, dict[str, str]]:
    """
    >>> urldecode('http://google.com/search?q=bar&x=y')
    ('http://google.com/search', {'q': 'bar', 'x': 'y'})
    >>> urldecode('http://google.com/')
    ('http://google.com/', {})
    """
    split_url = urllib.parse.urlsplit(url)
    items = urllib.parse.parse_qsl(split_url.query)
    d = {urllib.parse.unquote(k): urllib.parse.unquote_plus(v) for k, v in items}
    base = urllib.parse.urlunsplit(split_url._replace(query=""))
    return base, d


def changequery(url: str, **kw: Any) -> str:
    """
    >>> changequery('http://google.com/search?q=foo', q='bar', x='y')
    'http://google.com/search?q=bar&x=y'
    """
    base, params = urldecode(url)
    params.update(kw)
    return base + "?" + urllib.parse.urlencode(params)
