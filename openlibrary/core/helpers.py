"""Generic helper functions to use in the templates and the webapp."""

import json
import re
from collections.abc import Callable, Iterable
from datetime import date, datetime
from typing import Any
from urllib.parse import urlsplit

import babel
import babel.core
import babel.dates
import babel.numbers
import web
from babel.core import Locale

try:
    import genshi
    import genshi.filters
except ImportError:
    genshi = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

from infogami import config
from infogami.infobase.client import Nothing

# handy utility to parse ISO date strings
from infogami.infobase.utils import parse_datetime
from infogami.utils.view import safeint

# Helper functions that are added to `__all__` are exposed for use in templates
# in /openlibrary/plugins/upstream/utils.py setup()
__all__ = [
    "affiliate_id",
    "bookreader_host",
    "commify",
    "cond",
    "datestr",
    "datetimestr_utc",
    "days_since",
    "extract_year",
    "format_date",
    "json_encode",
    "parse_datetime",  # function imported from elsewhere
    "percentage",
    "private_collection_in",
    "private_collections",
    "safeint",  # function imported from elsewhere
    "safesort",
    "sanitize",
    "sprintf",
    "texsafe",
    "truncate",
    "urlsafe",
]
__docformat__ = "restructuredtext en"


def sanitize(html: str, encoding: str = 'utf8') -> str:
    """Removes unsafe tags and attributes from html and adds
    ``rel="nofollow"`` attribute to all external links.
    Using encoding=None if passing Unicode strings.
    encoding="utf8" matches default format for earlier versions of Genshi
    https://genshi.readthedocs.io/en/latest/upgrade/#upgrading-from-genshi-0-6-x-to-the-development-version
    """

    # Can't sanitize unless genshi module is available
    if genshi is None:
        return html

    def get_nofollow(name, event):
        attrs = event[1][1]

        if href := attrs.get('href', ''):
            # add rel=nofollow to all absolute links
            _, host, _, _, _ = urlsplit(href)
            if host:
                return 'nofollow'

    try:
        html = genshi.HTML(html, encoding=encoding)

    # except (genshi.ParseError, UnicodeDecodeError, UnicodeError) as e:
    # don't catch Unicode errors so we can tell if we're getting bytes
    except genshi.ParseError:
        if BeautifulSoup:
            # Bad html. Tidy it up using BeautifulSoup
            html = str(BeautifulSoup(html, "lxml"))
            try:
                html = genshi.HTML(html)
            except Exception:
                # Failed to sanitize.
                # We can't do any better than returning the original HTML, without sanitizing.
                return html
        else:
            raise

    stream = (
        html
        | genshi.filters.HTMLSanitizer()
        | genshi.filters.Transformer("//a").attr("rel", get_nofollow)
    )
    return stream.render()


class NothingEncoder(json.JSONEncoder):
    def default(self, obj):
        """Custom JSON encoder for handling Nothing values.

        Returns None if a value is a Nothing object. Otherwise,
        encode values using the default JSON encoder.
        """
        if isinstance(obj, Nothing):
            return None
        if isinstance(obj, date):
            return obj.isoformat()
        return super().default(obj)


def json_encode(d, **kw) -> str:
    """Calls json.dumps on the given data d.
    If d is a Nothing object, passes an empty list to json.dumps.

    Returns the json.dumps results.
    """
    return json.dumps([] if isinstance(d, Nothing) else d, **kw)


def safesort(
    iterable: Iterable, key: Callable | None = None, reverse: bool = False
) -> list:
    """Sorts heterogeneous of objects without raising errors.

    Sorting heterogeneous objects sometimes causes error. For example,
    datetime and Nones don't go well together. This function takes special
    care to make that work.
    """
    key = key or (lambda x: x)

    def safekey(x):
        k = key(x)
        return (k.__class__.__name__, k)

    return sorted(iterable, key=safekey, reverse=reverse)


def days_since(then: datetime, now: datetime | None = None) -> int:
    delta = then - (now or datetime.now())
    return abs(delta.days)


def datestr(
    then: datetime,
    now: datetime | None = None,
    lang: str | None = None,
    relative: bool = True,
) -> str:
    """Internationalized version of web.datestr."""
    lang = lang or web.ctx.lang
    if relative:
        if now is None:
            now = datetime.now()
        delta = then - now
        if abs(delta.days) < 4:  # Threshold from web.py
            return babel.dates.format_timedelta(
                delta, add_direction=True, locale=_get_babel_locale(lang)
            )
    return format_date(then, lang=lang)


def datetimestr_utc(then):
    return then.strftime("%Y-%m-%dT%H:%M:%SZ")


def format_date(date: datetime | None, lang: str | None = None) -> str:
    lang = lang or web.ctx.lang
    locale = _get_babel_locale(lang)
    return babel.dates.format_date(date, format="long", locale=locale)


def _get_babel_locale(lang: str) -> Locale:
    try:
        return babel.Locale(lang)
    except babel.core.UnknownLocaleError:
        return babel.Locale("en")


def sprintf(s, *a, **kw):
    """Handy utility for string replacements.

    >>> sprintf('hello %s', 'python')
    'hello python'
    >>> sprintf('hello %(name)s', name='python')
    'hello python'
    """
    if args := kw or a:
        return s % args
    else:
        return s


def cond(pred: Any, true_value: Any, false_value: Any = "") -> Any:
    """Lisp style cond function.

    Hanly to use instead of if-else expression.
    """
    return true_value if pred else false_value


def commify(number, lang=None):
    """localized version of web.commify"""
    try:
        lang = lang or web.ctx.get("lang") or "en"
        return babel.numbers.format_decimal(int(number), locale=lang)
    except Exception:
        return str(number)


def truncate(text: str, limit: int) -> str:
    """Truncate text and add ellipses if it longer than specified limit."""
    if not text:
        return ''
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def urlsafe(path: str) -> str:
    """Replaces the unsafe chars from path with underscores."""
    return _get_safepath_re().sub('_', path).strip('_')[:100]


@web.memoize
def _get_safepath_re():
    """Make regular expression that matches all unsafe chars."""
    # unsafe chars according to RFC 2396
    reserved = ";/?:@&=+$,"
    delims = '<>#%"'
    unwise = "{}|\\^[]`"
    space = ' \n\r'

    unsafe = reserved + delims + unwise + space
    pattern = '[%s]+' % "".join(re.escape(c) for c in unsafe)
    return re.compile(pattern)


_texsafe_map = {
    '"': r'\textquotedbl{}',
    '#': r'\#',
    '$': r'\$',
    '%': r'\%',
    '&': r'\&',
    '<': r'\textless{}',
    '>': r'\textgreater{}',
    '\\': r'\textbackslash{}',
    '^': r'\^{}',
    '_': r'\_{}',
    '{': r'\{',
    '}': r'\}',
    '|': r'\textbar{}',
    '~': r'\~{}',
}

_texsafe_re = None


def texsafe(text):
    """Escapes the special characters in the given text for using it in tex type setting.

    Tex (or Latex) uses some characters in the ascii character range for
    special notations. These characters must be escaped when occur in the
    regular text. This function escapes those special characters.

    The list of special characters and the latex command to typeset them can
    be found in `The Comprehensive LaTeX Symbol List`_.

    .. _The Comprehensive LaTeX Symbol List: http://www.ctan.org/tex-archive/info/symbols/comprehensive/symbols-a4.pdf
    """
    global _texsafe_re
    if _texsafe_re is None:
        pattern = "[%s]" % re.escape("".join(list(_texsafe_map)))
        _texsafe_re = re.compile(pattern)

    return _texsafe_re.sub(lambda m: _texsafe_map[m.group(0)], text)


def percentage(value, total):
    """Computes percentage.

    >>> percentage(1, 10)
    10.0
    >>> percentage(0, 0)
    0.0
    """
    return (value * 100.0) / total if total else 0.0


def uniq(values, key=None):
    """Returns the unique entries from the given values in the original order.

    The value of the optional `key` parameter should be a function that takes
    a single argument and returns a key to test the uniqueness.
    """
    key = key or (lambda x: x)
    s = set()
    result = []
    for v in values:
        k = key(v)
        if k not in s:
            s.add(k)
            result.append(v)
    return result


def affiliate_id(affiliate):
    return config.get('affiliate_ids', {}).get(affiliate, '')


def bookreader_host() -> str:
    return config.get('bookreader_host', '')


def private_collections() -> list[str]:
    """Collections which are lendable but should not be linked from OL
    TODO: Remove when we can handle institutional books"""
    return ['georgetown-university-law-library-rr']


def private_collection_in(collections: list[str]) -> bool:
    return any(x in private_collections() for x in collections)


def extract_year(input: str) -> str:
    """Extracts the year from an author's birth or death date."""
    if result := re.search(r'\d{4}', input):
        return result.group()
    else:
        return ''


def _get_helpers():
    _globals = globals()
    return web.storage((k, _globals[k]) for k in __all__)


# This must be at the end of this module
helpers = _get_helpers()
