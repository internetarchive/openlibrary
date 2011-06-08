"""Generic helper functions to use in the templates and the webapp.
"""
import web
import simplejson
import urlparse
import string
import re

import babel, babel.core, babel.dates, babel.numbers

try:
    import genshi
    import genshi.filters
except ImportError:
    genshi = None
    
try:
    from BeautifulSoup import BeautifulSoup
except ImportError:
    BeautifulSoup = None
    
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
    "sprintf", "cond", "commify", "truncate",
    "urlsafe", "texsafe",
    
    # functions imported from elsewhere
    "parse_datetime", "safeint"
]
__docformat__ = "restructuredtext en"

def sanitize(html):
    """Removes unsafe tags and attributes from html and adds
    ``rel="nofollow"`` attribute to all external links.
    """

    # Can't sanitize unless genshi module is available
    if genshi is None:
        return html
        
    def get_nofollow(name, event):
        attrs = event[1][1]
        href = attrs.get('href', '')

        if href:
            # add rel=nofollow to all absolute links
            _, host, _, _, _ = urlparse.urlsplit(href)
            if host:
                return 'nofollow'
                
    try:
        html = genshi.HTML(html)
    except genshi.ParseError:
        if BeautifulSoup:
            # Bad html. Tidy it up using BeautifulSoup
            html = str(BeautifulSoup(html))
            html = genshi.HTML(html)
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

def datestr(then, now=None, lang=None):
    """Internationalized version of web.datestr."""
    result = web.datestr(then, now)
    if not result:
        return result
    elif result[0] in string.digits: # eg: 2 milliseconds ago
        t, message = result.split(' ', 1)
        return _("%d " + message) % int(t)
    else:
        return format_date(then, lang=lang)


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
        return unicode(number)
        

def truncate(text, limit):
    """Truncate text and add ellipses if it longer than specified limit."""
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def urlsafe(path):
    """Replaces the unsafe chars from path with underscores.
    """
    return _get_safepath_re().sub('_', path).strip('_')

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
    return config.get('coverstore_url', 'http://covers.openlibrary.org').rstrip('/')


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
    
def _get_helpers():
    _globals = globals()
    return web.storage((k, _globals[k]) for k in __all__)
    

## This must be at the end of this module
helpers = _get_helpers()
