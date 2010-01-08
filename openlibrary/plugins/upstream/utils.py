import string, re
import web
import simplejson
import babel, babel.core, babel.dates
from UserDict import DictMixin

from infogami import config
from infogami.utils import view
from infogami.utils.view import render, public, _format
from infogami.utils.macro import macro
from infogami.utils.markdown import markdown
from infogami.utils.context import context
from infogami.infobase.client import Thing

from openlibrary.i18n import gettext as _
from openlibrary.plugins.openlibrary.code import sanitize

class MultiDict(DictMixin):
    """Ordered Dictionary that can store multiple values.
    
        >>> d = MultiDict()
        >>> d['x'] = 1
        >>> d['x'] = 2
        >>> d['y'] = 3
        >>> d['x']
        2
        >>> d['y']
        3
        >>> d['z']
        Traceback (most recent call last):
            ...
        KeyError: 'z'
        >>> d.keys()
        ['x', 'x', 'y']
        >>> d.items()
        [('x', 1), ('x', 2), ('y', 3)]
        >>> d.multi_items()
        [('x', [1, 2]), ('y', [3])]
    """
    def __init__(self, items=(), **kw):
        self._items = []
        
        for k, v in items:
            self[k] = v
        self.update(kw)
    
    def __getitem__(self, key):
        values = self.getall(key)
        if values:
            return values[-1]
        else:
            raise KeyError, key
    
    def __setitem__(self, key, value):
        self._items.append((key, value))
        
    def __delitem__(self, key):
        self._items = [(k, v) for k, v in self._items if k != key]
        
    def getall(self, key):
        return [v for k, v in self._items if k == key]
        
    def keys(self):
        return [k for k, v in self._items]
        
    def values(self):
        return [v for k, v in self._items]
        
    def items(self):
        return self._items[:]
        
    def multi_items(self):
        """Returns items as tuple of key and a list of values."""
        items = []
        d = {}
        
        for k, v in self._items:
            if k not in d:
                d[k] = []
                items.append((k, d[k]))
            d[k].append(v)
        return items
        
@macro
@public
def render_template(name, *a, **kw):
    if "." in name:
        name = name.rsplit(".", 1)[0]
    return render[name](*a, **kw)
    
@public
def json_encode(d):
    return simplejson.dumps(d)
    
def unflatten(d, seperator="--"):
    """Convert flattened data into nested form.
    
        >>> unflatten({"a": 1, "b--x": 2, "b--y": 3, "c--0": 4, "c--1": 5})
        {'a': 1, 'c': [4, 5], 'b': {'y': 3, 'x': 2}}
        >>> unflatten({"a--0--x": 1, "a--0--y": 2, "a--1--x": 3, "a--1--y": 4})
        {'a': [{'x': 1, 'y': 2}, {'x': 3, 'y': 4}]}
        
    """
    def isint(k):
        try:
            int(k)
            return True
        except ValueError:
            return False
        
    def setvalue(data, k, v):
        if '--' in k:
            k, k2 = k.split(seperator, 1)
            setvalue(data.setdefault(k, {}), k2, v)
        else:
            data[k] = v
            
    def makelist(d):
        """Convert d into a list if all the keys of d are integers."""
        if isinstance(d, dict):
            if all(isint(k) for k in d.keys()):
                return [makelist(d[k]) for k in sorted(d.keys(), key=int)]
            else:
                return web.storage((k, makelist(v)) for k, v in d.items())
        else:
            return d
            
    d2 = {}
    for k, v in d.items():
        setvalue(d2, k, v)
    return makelist(d2)
    
@public
def radio_input(checked=False, **params):
    params['type'] = 'radio'
    if checked:
        params['checked'] = "checked"
    return "<input %s />" % " ".join(['%s="%s"' % (k, web.websafe(v)) for k, v in params.items()])
    
@public
def radio_list(name, args, value):
    html = []
    for arg in args:
        if isinstance(arg, tuple):
            arg, label = arg
        else:
            label = arg
        html.append(radio_input())
        
@public
def get_coverstore_url():
    return config.get('coverstore_url', 'http://covers.openlibrary.org').rstrip('/')


@public
def get_history(page):
    """Returns initial and most recent history of given page.
    
    If the page has more than 5 revisions, first 2 and recent 3 changes are returned. 
    If the page has 5 or less than 
    """
    h = web.storage(revision=page.revision)
    if h.revision < 5:
        h.recent = web.ctx.site.versions({"key": page.key, "limit": 5})
        h.initial = []
    else:
        h.initial = web.ctx.site.versions({"key": page.key, "limit": 2, "offset": h.revision-2})
        h.recent = web.ctx.site.versions({"key": page.key, "limit": 3})
    return h

@public
def get_recent_author(doc):
    versions = web.ctx.site.versions({'key': doc.key, 'limit': 1})
    if versions:
        return versions[0].author

@public
def get_recent_accounts(limit=5, offset=0):
    versions = web.ctx.site.versions({'type': '/type/user', 'revision': 1, 'limit': limit, 'offset': offset})
    return web.ctx.site.get_many([v.key for v in versions])

def get_locale():
    try:
        return babel.Locale(web.ctx.get("lang") or "en")
    except babel.core.UnknownLocaleError:
        return babel.Locale("en")
    
@public
def datestr(then, now=None):
    """Internationalized version of web.datestr."""
    result = web.datestr(then, now)
    if result[0] in string.digits: # eg: 2 milliseconds ago
        t, message = result.split(' ', 1)
        return _("%d " + message) % int(t)
    else:
        return babel.dates.format_date(then, format="long", locale=get_locale())    
 
@public     
def truncate(text, limit):
    """Truncate text and add ellipses if it longer than specified limit."""
    if len(text) < limit:
        return text
    return text[:limit] + "..."
    
@public
def process_version(v):
    """Looks at the version and adds machine_comment required for showing "View MARC" link."""
    importers = ['/people/ImportBot', '/people/EdwardBot']
    if v.author and v.author.key in importers and v.key.startswith('/books/') and not v.get('machine_comment'):
        thing = v.get('thing') or web.ctx.site.get(v.key, v.revision)
        if thing.source_records and v.revision == 1 or (v.comment and v.comment.lower() == "found a matching marc record"):
            marc = thing.source_records[-1]
            if marc.startswith('marc:'):
                v.machine_comment = marc[len("marc:"):]
            else:
                v.machine_comment = marc
    return v

@public
def cond(pred, true_value, false_value=""):
    if pred:
        return true_value
    else:
        return false_value

@public
def is_thing(t):
    return isinstance(t, Thing)
    
@public
def putctx(key, value):
    """Save a value in the context."""
    context[key] = value
    return ""
    
def pad(seq, size, e=None):
    """
        >>> pad([1, 2], 4, 0)
        [1, 2, 0, 0]
    """
    seq = seq[:]
    while len(seq) < size:
        seq.append(e)
    return seq

def parse_toc_row(line):
    """Parse one row of table of contents.

        >>> def f(text):
        ...     d = parse_toc_row(text)
        ...     return (d['level'], d['label'], d['title'], d['pagenum'])
        ...
        >>> f("* chapter 1 | Welcome to the real world! | 2")
        (1, 'chapter 1', 'Welcome to the real world!', '2')
        >>> f("Welcome to the real world!")
        (0, '', 'Welcome to the real world!', '')
        >>> f("** | Welcome to the real world! | 2")
        (2, '', 'Welcome to the real world!', '2')
        >>> f("|Preface | 1")
        (0, '', 'Preface', '1')
        >>> f("1.1 | Apple")
        (0, '1.1', 'Apple', '')
    """
    RE_LEVEL = web.re_compile("(\**)(.*)")
    level, text = RE_LEVEL.match(line.strip()).groups()

    if "|" in text:
        tokens = text.split("|", 2)
        label, title, page = pad(tokens, 3, '')
    else:
        title = text
        label = page = ""

    return web.storage(level=len(level), label=label.strip(), title=title.strip(), pagenum=page.strip())

def parse_toc(text):
    """Parses each line of toc"""
    if text is None:
        return []
    return [parse_toc_row(line) for line in text.splitlines() if line.strip()]
    

_languages = None
    
@public
def get_languages():
    global _languages
    if _languages is None:
        keys = web.ctx.site.things({"type": "/type/language", "key~": "/languages/*", "limit": 1000})
        _languages = [web.storage(name=d.name, code=d.code) for d in web.ctx.site.get_many(keys)]
    return _languages
    
# regexp to match urls and emails. 
# Adopted from github-flavored-markdown (BSD-style open source license)
# http://github.com/github/github-flavored-markdown/blob/gh-pages/scripts/showdown.js#L158
AUTOLINK_RE = r'''(^|\s)(https?\:\/\/[^"\s<>]*[^.,;'">\:\s\<\>\)\]\!]|[a-z0-9_\-+=.]+@[a-z0-9\-]+(?:\.[a-z0-9-]+)+)'''

LINK_REFERENCE_RE = re.compile(r' *\[[^\[\] ]*\] *:')

class LineBreaksPreprocessor(markdown.Preprocessor):
    def run(self, lines) :
        for i in range(len(lines)-1):
            # append <br/> to all lines expect blank lines and the line before blankline.
            if (lines[i].strip() and lines[i+1].strip()
                and not markdown.RE.regExp['tabbed'].match(lines[i])
                and not LINK_REFERENCE_RE.match(lines[i])):
                lines[i] += "<br />"
        return lines

LINE_BREAKS_PREPROCESSOR = LineBreaksPreprocessor()

class AutolinkPreprocessor(markdown.Preprocessor):
    rx = re.compile(AUTOLINK_RE)
    def run(self, lines):
        for i in range(len(lines)):
            if not markdown.RE.regExp['tabbed'].match(lines[i]):
                lines[i] = self.rx.sub(r'\1<\2>', lines[i])
        return lines

AUTOLINK_PREPROCESSOR = AutolinkPreprocessor()
    
class OLMarkdown(markdown.Markdown):
    """Open Library flavored Markdown, inspired by [Github Flavored Markdown][GFM].
    
    GFM: http://github.github.com/github-flavored-markdown/

    Differences from traditional Markdown:
    * new lines in paragraph are treated as line breaks
    * URLs are autolinked
    * generated HTML is sanitized    
    """
    def __init__(self, *a, **kw):
        markdown.Markdown.__init__(self, *a, **kw)
        self._patch()
        
    def _patch(self):
        p = self.preprocessors
        p[p.index(markdown.LINE_BREAKS_PREPROCESSOR)] = LINE_BREAKS_PREPROCESSOR
        p.append(AUTOLINK_PREPROCESSOR)
        
    def convert(self):
        html = markdown.Markdown.convert(self)
        return sanitize(html)
        
def get_markdown(text, safe_mode=False):
    md = OLMarkdown(source=text, safe_mode=safe_mode)
    view._register_mdx_extensions(md)
    md.postprocessors += view.wiki_processors
    return md

def setup():
    """Do required initialization"""
    # monkey-patch get_markdown to use OL Flavored Markdown
    view.get_markdown = get_markdown
    
if __name__ == '__main__':
    import doctest
    doctest.testmod()
