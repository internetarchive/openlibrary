"""Generic helper functions to use in the templates and the webapp.
"""
import web
from datetime import datetime
import simplejson

import re

from six.moves.urllib.parse import urlsplit

import babel
import babel.core
import babel.dates
import babel.numbers

try:
    import genshi
    import genshi.filters
except ImportError:
    genshi = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

import six

from infogami import config

# handy utility to parse ISO date strings
from infogami.infobase.utils import parse_datetime
from infogami.utils.view import safeint

# TODO: i18n should be moved to core or infogami
from openlibrary.i18n import gettext as _

__all__ = [
    "sanitize",
    "json_encode",
    "safesort",
    "datestr", "format_date",
    "sprintf", "cond", "commify", "truncate", "datetimestr_utc",
    "urlsafe", "texsafe",
    "percentage", "affiliate_id", "bookreader_host",
    "private_collections", "private_collection_in",

    # functions imported from elsewhere
    "parse_datetime", "safeint"
]
__docformat__ = "restructuredtext en"

def sanitize(html, encoding='utf8'):
    """Removes unsafe tags and attributes from html and adds
    ``rel="nofollow"`` attribute to all external links.
    Using encoding=None if passing unicode strings e.g. for Python 3.
    encoding="utf8" matches default format for earlier versions of Genshi
    https://genshi.readthedocs.io/en/latest/upgrade/#upgrading-from-genshi-0-6-x-to-the-development-version
    """

    # Can't sanitize unless genshi module is available
    if genshi is None:
        return html

    def get_nofollow(name, event):
        attrs = event[1][1]
        href = attrs.get('href', '')

        if href:
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

    stream = html \
        | genshi.filters.HTMLSanitizer() \
        | genshi.filters.Transformer("//a").attr("rel", get_nofollow)
    return stream.render()


def json_encode(d, **kw):
    """Same as simplejson.dumps.
    """
    return simplejson.dumps(d, **kw)


def safesort(iterable, key=None, reverse=False):
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

def datestr(then, now=None, lang=None, relative=True):
    """Internationalized version of web.datestr."""
    lang = lang or web.ctx.get('lang') or "en"
    if relative:
        if now is None:
            now = datetime.now()
        delta = then - now
        if abs(delta.days) < 4: # Threshold from web.py
            return babel.dates.format_timedelta(delta,
                                                add_direction=True,
                                                locale=_get_babel_locale(lang))
    return format_date(then, lang=lang)


def datetimestr_utc(then):
    return then.strftime("%Y-%m-%dT%H:%M:%SZ")

def format_date(date, lang=None):
    lang = lang or web.ctx.get('lang') or "en"
    locale = _get_babel_locale(lang)
    return babel.dates.format_date(date, format="long", locale=locale)

def _get_babel_locale(lang):
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
    args = kw or a
    if args:
        return s % args
    else:
        return s


def cond(pred, true_value, false_value=""):
    """Lisp style cond function.

    Hanly to use instead of if-else expression.
    """
    if pred:
        return true_value
    else:
        return false_value


def commify(number, lang=None):
    """localized version of web.commify"""
    try:
        lang = lang or web.ctx.get("lang") or "en"
        return babel.numbers.format_number(int(number), lang)
    except:
        return six.text_type(number)


def truncate(text, limit):
    """Truncate text and add ellipses if it longer than specified limit."""
    if not text:
        return ''
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def urlsafe(path):
    """Replaces the unsafe chars from path with underscores.
    """
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


def get_coverstore_url():
    """Returns the base url of coverstore by looking at the config."""
    return config.get('coverstore_url', 'https://covers.openlibrary.org').rstrip('/')


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
        pattern = "[%s]" % re.escape("".join(_texsafe_map.keys()))
        _texsafe_re = re.compile(pattern)

    return _texsafe_re.sub(lambda m: _texsafe_map[m.group(0)], text)

def percentage(value, total):
    """Computes percentage.

        >>> percentage(1, 10)
        10.0
        >>> percentage(0, 0)
        0.0
    """
    if total == 0:
        return 0
    else:
        return (value * 100.0)/total

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

def bookreader_host():
    return config.get('bookreader_host', '')

def private_collections():
    """Collections which are lendable but should not be linked from OL
    TODO: Remove when we can handle institutional books"""
    return ['georgetown-university-law-library-rr']

def private_collection_in(collections):
    return any(x in private_collections() for x in collections)

def _get_helpers():
    _globals = globals()
    return web.storage((k, _globals[k]) for k in __all__)


## This must be at the end of this module
helpers = _get_helpers()
