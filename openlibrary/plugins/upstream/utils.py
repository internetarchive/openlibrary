import functools
from typing import Iterable, List, Union, Tuple, Any
import unicodedata

import web
import json
import babel
import babel.core
import babel.dates
from babel.lists import format_list
from collections import defaultdict
import re
import random
import xml.etree.ElementTree as etree
import datetime
import logging
from html.parser import HTMLParser
from typing import Optional

import requests

from html import unescape
import urllib
from collections.abc import MutableMapping
from urllib.parse import (
    parse_qs,
    urlencode as parse_urlencode,
    urlparse,
    urlunparse,
)

from infogami import config
from infogami.utils import view, delegate, stats
from infogami.utils.view import render, get_template, public, query_param
from infogami.utils.macro import macro
from infogami.utils.context import context
from infogami.infobase.client import Thing, Changeset, storify

from openlibrary.core.helpers import commify, parse_datetime, truncate
from openlibrary.core.middleware import GZipMiddleware
from openlibrary.core import cache, ab


class MultiDict(MutableMapping):
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
    >>> list(d)
    ['x', 'x', 'y']
    >>> list(d.items())
    [('x', 1), ('x', 2), ('y', 3)]
    >>> list(d.multi_items())
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
            raise KeyError(key)

    def __setitem__(self, key, value):
        self._items.append((key, value))

    def __delitem__(self, key):
        self._items = [(k, v) for k, v in self._items if k != key]

    def __iter__(self):
        yield from self.keys()

    def __len__(self):
        return len(list(self.keys()))

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


def kebab_case(upper_camel_case):
    """
    :param str upper_camel_case: Text in upper camel case (e.g. "HelloWorld")
    :return: text in kebab case (e.g. 'hello-world')

    >>> kebab_case('HelloWorld')
    'hello-world'
    >>> kebab_case("MergeUI")
    'merge-u-i'
    """
    parts = re.findall(r'[A-Z][^A-Z]*', upper_camel_case)
    return '-'.join(parts).lower()


@public
def render_component(name, attrs=None, json_encode=True):
    """
    :param str name: Name of the component (excluding extension)
    :param dict attrs: attributes to add to the component element
    """
    from openlibrary.plugins.upstream.code import static_url

    attrs = attrs or {}
    attrs_str = ''
    for (key, val) in attrs.items():
        if json_encode and isinstance(val, dict) or isinstance(val, list):
            val = json.dumps(val)
            # On the Vue side use decodeURIComponent to decode
            val = urllib.parse.quote(val)
        attrs_str += f' {key}="{val}"'
    html = ''
    included = web.ctx.setdefault("included-components", [])

    if len(included) == 0:
        # Need to include Vue
        html += '<script src="%s"></script>' % static_url('build/vue.js')

    if name not in included:
        url = static_url('build/components/production/ol-%s.min.js' % name)
        html += '<script src="%s"></script>' % url
        included.append(name)

    html += '<ol-{name} {attrs}></ol-{name}>'.format(
        name=kebab_case(name),
        attrs=attrs_str,
    )
    return html


@public
def get_error(name, *args):
    """Return error with the given name from errors.tmpl template."""
    return get_message_from_template("errors", name, args)


@public
def get_message(name, *args):
    """Return message with given name from messages.tmpl template"""
    return get_message_from_template("messages", name, args)


def get_message_from_template(template_name, name, args):
    d = render_template(template_name).get("messages", {})
    msg = d.get(name) or name.lower().replace("_", " ")

    if msg and args:
        return msg % args
    else:
        return msg


@public
def list_recent_pages(path, limit=100, offset=0):
    """Lists all pages with name path/* in the order of last_modified."""
    q = {}

    q['key~'] = path + '/*'
    # don't show /type/delete and /type/redirect
    q['a:type!='] = '/type/delete'
    q['b:type!='] = '/type/redirect'

    q['sort'] = 'key'
    q['limit'] = limit
    q['offset'] = offset
    q['sort'] = '-last_modified'
    # queries are very slow with != conditions
    # q['type'] != '/type/delete'
    return web.ctx.site.get_many(web.ctx.site.things(q))


@public
def commify_list(items: Iterable[Any]):
    # Not sure why lang is sometimes ''
    lang = web.ctx.lang or 'en'
    # If the list item is a template/html element, we strip it
    # so that there is no space before the comma.
    return format_list([str(x).strip() for x in items], locale=lang)


@public
def json_encode(d):
    return json.dumps(d)


def unflatten(d, separator="--"):
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
            k, k2 = k.split(separator, 1)
            setvalue(data.setdefault(k, {}), k2, v)
        else:
            data[k] = v

    def makelist(d):
        """Convert d into a list if all the keys of d are integers."""
        if isinstance(d, dict):
            if all(isint(k) for k in d):
                return [makelist(d[k]) for k in sorted(d, key=int)]
            else:
                return web.storage((k, makelist(v)) for k, v in d.items())
        else:
            return d

    d2 = {}
    for k, v in d.items():
        setvalue(d2, k, v)
    return makelist(d2)


def fuzzy_find(value, options, stopwords=None):
    stopwords = stopwords or []
    """Try find the option nearest to the value.

        >>> fuzzy_find("O'Reilly", ["O'Reilly Inc", "Addison-Wesley"])
        "O'Reilly Inc"
    """
    if not options:
        return value

    rx = web.re_compile(r"[-_\.&, ]+")

    # build word frequency
    d = defaultdict(list)
    for option in options:
        for t in rx.split(option):
            d[t].append(option)

    # find score for each option
    score = defaultdict(lambda: 0)
    for t in rx.split(value):
        if t.lower() in stopwords:
            continue
        for option in d[t]:
            score[option] += 1

    # take the option with maximum score
    return max(options, key=score.__getitem__)


@public
def radio_input(checked=False, **params):
    params['type'] = 'radio'
    if checked:
        params['checked'] = "checked"
    return "<input %s />" % " ".join(
        [f'{k}="{web.websafe(v)}"' for k, v in params.items()]
    )


@public
def radio_list(name, args, value):
    html = []
    for arg in args:
        if isinstance(arg, tuple):
            arg, label = arg
        else:
            label = arg
        html.append(radio_input())


def get_coverstore_url() -> str:
    return config.get('coverstore_url', 'https://covers.openlibrary.org').rstrip('/')


@public
def get_coverstore_public_url() -> str:
    return config.get('coverstore_public_url', get_coverstore_url()).rstrip('/')


def _get_changes_v1_raw(query, revision=None):
    """Returns the raw versions response.

    Revision is taken as argument to make sure a new cache entry is used when a new revision of the page is created.
    """
    if 'env' not in web.ctx:
        delegate.fakeload()

    versions = web.ctx.site.versions(query)

    for v in versions:
        v.created = v.created.isoformat()
        v.author = v.author and v.author.key

        # XXX-Anand: hack to avoid too big data to be stored in memcache.
        # v.changes is not used and it contrinutes to memcache bloat in a big way.
        v.changes = '[]'

    return versions


def get_changes_v1(query, revision=None):
    # uses the cached function _get_changes_v1_raw to get the raw data
    # and processes to before returning.
    def process(v):
        v = web.storage(v)
        v.created = parse_datetime(v.created)
        v.author = v.author and web.ctx.site.get(v.author, lazy=True)
        return v

    return [process(v) for v in _get_changes_v1_raw(query, revision)]


def _get_changes_v2_raw(query, revision=None):
    """Returns the raw recentchanges response.

    Revision is taken as argument to make sure a new cache entry is used when a new revision of the page is created.
    """
    if 'env' not in web.ctx:
        delegate.fakeload()

    changes = web.ctx.site.recentchanges(query)
    return [c.dict() for c in changes]


# XXX-Anand: disabled temporarily to avoid too much memcache usage.
# _get_changes_v2_raw = cache.memcache_memoize(_get_changes_v2_raw, key_prefix="upstream._get_changes_v2_raw", timeout=10*60)


def get_changes_v2(query, revision=None):
    page = web.ctx.site.get(query['key'])

    def first(seq, default=None):
        try:
            return next(seq)
        except StopIteration:
            return default

    def process_change(change):
        change = Changeset.create(web.ctx.site, storify(change))
        change.thing = page
        change.key = page.key
        change.revision = first(c.revision for c in change.changes if c.key == page.key)
        change.created = change.timestamp

        change.get = change.__dict__.get
        change.get_comment = lambda: get_comment(change)
        change.machine_comment = change.data.get("machine_comment")

        return change

    def get_comment(change):
        t = get_template("recentchanges/" + change.kind + "/comment") or get_template(
            "recentchanges/default/comment"
        )
        return t(change, page)

    query['key'] = page.key
    changes = _get_changes_v2_raw(query, revision=page.revision)
    return [process_change(c) for c in changes]


def get_changes(query, revision=None):
    return get_changes_v2(query, revision=revision)


@public
def get_history(page):
    h = web.storage(
        revision=page.revision, lastest_revision=page.revision, created=page.created
    )
    if h.revision < 5:
        h.recent = get_changes({"key": page.key, "limit": 5}, revision=page.revision)
        h.initial = h.recent[-1:]
        h.recent = h.recent[:-1]
    else:
        h.initial = get_changes(
            {"key": page.key, "limit": 1, "offset": h.revision - 1},
            revision=page.revision,
        )
        h.recent = get_changes({"key": page.key, "limit": 4}, revision=page.revision)

    return h


@public
def get_version(key, revision):
    try:
        return web.ctx.site.versions({"key": key, "revision": revision, "limit": 1})[0]
    except IndexError:
        return None


@public
def get_recent_author(doc):
    versions = get_changes_v1(
        {'key': doc.key, 'limit': 1, "offset": 0}, revision=doc.revision
    )
    if versions:
        return versions[0].author


@public
def get_recent_accounts(limit=5, offset=0):
    versions = web.ctx.site.versions(
        {'type': '/type/user', 'revision': 1, 'limit': limit, 'offset': offset}
    )
    return web.ctx.site.get_many([v.key for v in versions])


def get_locale():
    try:
        return babel.Locale(web.ctx.get("lang") or "en")
    except babel.core.UnknownLocaleError:
        return babel.Locale("en")


@public
def process_version(v):
    """Looks at the version and adds machine_comment required for showing "View MARC" link."""
    comments = [
        "found a matching marc record",
        "add publisher and source",
    ]
    if v.key.startswith('/books/') and not v.get('machine_comment'):
        thing = v.get('thing') or web.ctx.site.get(v.key, v.revision)
        if (
            thing.source_records
            and v.revision == 1
            or (v.comment and v.comment.lower() in comments)
        ):
            marc = thing.source_records[-1]
            if marc.startswith('marc:'):
                v.machine_comment = marc[len("marc:") :]
            else:
                v.machine_comment = marc
    return v


@public
def is_thing(t):
    return isinstance(t, Thing)


@public
def putctx(key, value):
    """Save a value in the context."""
    context[key] = value
    return ""


class Metatag:
    def __init__(self, tag="meta", **attrs):
        self.tag = tag
        self.attrs = attrs

    def __str__(self):
        attrs = ' '.join(f'{k}="{websafe(v)}"' for k, v in self.attrs.items())
        return f'<{self.tag} {attrs} />'

    def __repr__(self):
        return 'Metatag(%s)' % str(self)


@public
def add_metatag(tag="meta", **attrs):
    context.setdefault('metatags', [])
    context.metatags.append(Metatag(tag, **attrs))


@public
def url_quote(text):
    if isinstance(text, str):
        text = text.encode('utf8')
    return urllib.parse.quote_plus(text)


@public
def urlencode(dict_or_list_of_tuples: Union[dict, list[tuple[str, Any]]]) -> str:
    """
    You probably want to use this, if you're looking to urlencode parameters. This will
    encode things to utf8 that would otherwise cause urlencode to error.
    """
    from urllib.parse import urlencode as og_urlencode

    tuples = dict_or_list_of_tuples
    if isinstance(dict_or_list_of_tuples, dict):
        tuples = list(dict_or_list_of_tuples.items())
    params = [(k, v.encode('utf-8') if isinstance(v, str) else v) for (k, v) in tuples]
    return og_urlencode(params)


@public
def entity_decode(text):
    return unescape(text)


@public
def set_share_links(url='#', title='', view_context=None):
    """
    Constructs list share links for social platforms and assigns to view context attribute

    Args (all required):
        url (str or unicode) - complete canonical url to page being shared
        title (str or unicode) - title of page being shared
        view_context (object that has/can-have share_links attribute)
    """
    encoded_url = url_quote(url)
    text = url_quote("Check this out: " + entity_decode(title))
    links = [
        {
            'text': 'Facebook',
            'url': 'https://www.facebook.com/sharer/sharer.php?u=' + encoded_url,
        },
        {
            'text': 'Twitter',
            'url': f'https://twitter.com/intent/tweet?url={encoded_url}&via=openlibrary&text={text}',
        },
        {
            'text': 'Pinterest',
            'url': f'https://pinterest.com/pin/create/link/?url={encoded_url}&description={text}',
        },
    ]
    view_context.share_links = links


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
    RE_LEVEL = web.re_compile(r"(\**)(.*)")
    level, text = RE_LEVEL.match(line.strip()).groups()

    if "|" in text:
        tokens = text.split("|", 2)
        label, title, page = pad(tokens, 3, '')
    else:
        title = text
        label = page = ""

    return web.storage(
        level=len(level), label=label.strip(), title=title.strip(), pagenum=page.strip()
    )


def parse_toc(text):
    """Parses each line of toc"""
    if text is None:
        return []
    return [parse_toc_row(line) for line in text.splitlines() if line.strip(" |")]


def safeget(func):
    """
    TODO: DRY with solrbuilder copy
    >>> safeget(lambda: {}['foo'])
    >>> safeget(lambda: {}['foo']['bar'][0])
    >>> safeget(lambda: {'foo': []}['foo'][0])
    >>> safeget(lambda: {'foo': {'bar': [42]}}['foo']['bar'][0])
    42
    >>> safeget(lambda: {'foo': 'blah'}['foo']['bar'])
    """
    try:
        return func()
    except (KeyError, IndexError, TypeError):
        return None


def strip_accents(s: str) -> str:
    # http://stackoverflow.com/questions/517923/what-is-the-best-way-to-remove-accents-in-a-python-unicode-string
    try:
        s.encode('ascii')
        return s
    except UnicodeEncodeError:
        return ''.join(
            c
            for c in unicodedata.normalize('NFD', s)
            if unicodedata.category(c) != 'Mn'
        )


@functools.cache
def get_languages():
    keys = web.ctx.site.things({"type": "/type/language", "limit": 1000})
    return {lang.key: lang for lang in web.ctx.site.get_many(keys)}


def autocomplete_languages(prefix: str):
    def normalize(s: str) -> str:
        return strip_accents(s).lower()

    prefix = normalize(prefix)
    user_lang = web.ctx.lang or 'en'
    for lang in get_languages().values():
        user_lang_name = safeget(lambda: lang['name_translated'][user_lang][0])
        if user_lang_name and normalize(user_lang_name).startswith(prefix):
            yield web.storage(
                key=lang.key,
                code=lang.code,
                name=user_lang_name,
            )
            continue

        lang_iso_code = safeget(lambda: lang['identifiers']['iso_639_1'][0])
        native_lang_name = safeget(lambda: lang['name_translated'][lang_iso_code][0])
        if native_lang_name and normalize(native_lang_name).startswith(prefix):
            yield web.storage(
                key=lang.key,
                code=lang.code,
                name=native_lang_name,
            )
            continue

        if normalize(lang.name).startswith(prefix):
            yield web.storage(
                key=lang.key,
                code=lang.code,
                name=lang.name,
            )
            continue


def get_language(lang_or_key: Union[Thing, str]) -> Thing:
    if isinstance(lang_or_key, str):
        return get_languages()[lang_or_key]
    else:
        return lang_or_key


@public
def get_language_name(lang_or_key: Union[Thing, str]):
    user_lang = web.ctx.lang or 'en'
    lang = get_language(lang_or_key)
    return safeget(lambda: lang['name_translated'][user_lang][0]) or lang.name


@public
def get_author_config():
    return _get_author_config()


@web.memoize
def _get_author_config():
    """Returns the author config.

    The results are cached on the first invocation.
    Any changes to /config/author page require restarting the app.

    """
    thing = web.ctx.site.get('/config/author')
    if hasattr(thing, "identifiers"):
        identifiers = [web.storage(t.dict()) for t in thing.identifiers if 'name' in t]
    else:
        identifiers = {}
    return web.storage(identifiers=identifiers)


@public
def get_edition_config():
    return _get_edition_config()


@web.memoize
def _get_edition_config():
    """Returns the edition config.

    The results are cached on the first invocation. Any changes to /config/edition page require restarting the app.

    This is is cached because fetching and creating the Thing object was taking about 20ms of time for each book request.
    """
    thing = web.ctx.site.get('/config/edition')
    classifications = [
        web.storage(t.dict()) for t in thing.classifications if 'name' in t
    ]
    identifiers = [web.storage(t.dict()) for t in thing.identifiers if 'name' in t]
    roles = thing.roles
    return web.storage(
        classifications=classifications, identifiers=identifiers, roles=roles
    )


from openlibrary.core.olmarkdown import OLMarkdown


def get_markdown(text, safe_mode=False):
    md = OLMarkdown(source=text, safe_mode=safe_mode)
    view._register_mdx_extensions(md)
    md.postprocessors += view.wiki_processors
    return md


class HTML(str):
    def __init__(self, html):
        str.__init__(self, web.safeunicode(html))

    def __repr__(self):
        return "<html: %s>" % str.__repr__(self)


_websafe = web.websafe


def websafe(text):
    if isinstance(text, HTML):
        return text
    elif isinstance(text, web.template.TemplateResult):
        return web.safestr(text)
    else:
        return _websafe(text)


from openlibrary.plugins.upstream import adapter
from openlibrary.utils.olcompress import OLCompressor
from openlibrary.utils import olmemcache
import memcache


class UpstreamMemcacheClient:
    """Wrapper to memcache Client to handle upstream specific conversion and OL specific compression.
    Compatible with memcache Client API.
    """

    def __init__(self, servers):
        self._client = memcache.Client(servers)
        compressor = OLCompressor()
        self.compress = compressor.compress

        def decompress(*args, **kw):
            d = json.loads(compressor.decompress(*args, **kw))
            return json.dumps(adapter.unconvert_dict(d))

        self.decompress = decompress

    def get(self, key):
        key = adapter.convert_key(key)
        if key is None:
            return None

        try:
            value = self._client.get(web.safestr(key))
        except memcache.Client.MemcachedKeyError:
            return None

        return value and self.decompress(value)

    def get_multi(self, keys):
        keys = [adapter.convert_key(k) for k in keys]
        keys = [web.safestr(k) for k in keys]

        d = self._client.get_multi(keys)
        return {
            web.safeunicode(adapter.unconvert_key(k)): self.decompress(v)
            for k, v in d.items()
        }


if config.get('upstream_memcache_servers'):
    olmemcache.Client = UpstreamMemcacheClient  # type: ignore[assignment, misc]
    # set config.memcache_servers only after olmemcache.Client is updated
    config.memcache_servers = config.upstream_memcache_servers  # type: ignore[attr-defined]


def _get_recent_changes():
    site = web.ctx.get('site') or delegate.create_site()
    web.ctx.setdefault("ip", "127.0.0.1")

    # The recentchanges can have multiple revisions for a document if it has been
    # modified more than once.  Take only the most recent revision in that case.
    visited = set()

    def is_visited(key):
        if key in visited:
            return True
        else:
            visited.add(key)
            return False

    # ignore reverts
    re_revert = web.re_compile(r"reverted to revision \d+")

    def is_revert(r):
        return re_revert.match(r.comment or "")

    # take the 100 recent changes, filter them and take the first 50
    q = {"bot": False, "limit": 100}
    result = site.versions(q)
    result = [r for r in result if not is_visited(r.key) and not is_revert(r)]
    result = result[:50]

    def process_thing(thing):
        t = web.storage()
        for k in ["key", "title", "name", "displayname"]:
            t[k] = thing[k]
        t['type'] = web.storage(key=thing.type.key)
        return t

    for r in result:
        r.author = r.author and process_thing(r.author)
        r.thing = process_thing(site.get(r.key, r.revision))

    return result


def _get_recent_changes2():
    """New recent changes for around the library.

    This function returns the message to display for each change.
    The message is get by calling `recentchanges/$kind/message.html` template.

    If `$var ignore=True` is set by the message template, the change is ignored.
    """
    if 'env' not in web.ctx:
        delegate.fakeload()

    q = {"bot": False, "limit": 100}
    changes = web.ctx.site.recentchanges(q)

    def is_ignored(c):
        return (
            # c.kind=='update' allow us to ignore update recent changes on people
            c.kind == 'update'
            or
            # ignore change if author has been deleted (e.g. spammer)
            (c.author and c.author.type.key == '/type/delete')
        )

    def render(c):
        t = get_template("recentchanges/" + c.kind + "/message") or get_template(
            "recentchanges/default/message"
        )
        return t(c)

    messages = [render(c) for c in changes if not is_ignored(c)]
    messages = [m for m in messages if str(m.get("ignore", "false")).lower() != "true"]
    return messages


_get_recent_changes = web.memoize(_get_recent_changes, expires=5 * 60, background=True)
_get_recent_changes2 = web.memoize(
    _get_recent_changes2, expires=5 * 60, background=True
)


@public
def get_random_recent_changes(n):
    if "recentchanges_v2" in web.ctx.get("features", []):
        changes = _get_recent_changes2()
    else:
        changes = _get_recent_changes()

    _changes = random.sample(changes, n) if len(changes) > n else changes
    for i, change in enumerate(_changes):
        _changes[i]['__body__'] = (
            _changes[i]['__body__'].replace('<script>', '').replace('</script>', '')
        )
    return _changes


def _get_blog_feeds():
    url = "https://blog.openlibrary.org/feed/"
    try:
        stats.begin("get_blog_feeds", url=url)
        tree = etree.fromstring(requests.get(url).text)
    except Exception:
        # Handle error gracefully.
        logging.getLogger("openlibrary").error(
            "Failed to fetch blog feeds", exc_info=True
        )
        return []
    finally:
        stats.end()

    def parse_item(item):
        pubdate = datetime.datetime.strptime(
            item.find("pubDate").text, '%a, %d %b %Y %H:%M:%S +0000'
        ).isoformat()
        return dict(
            title=item.find("title").text, link=item.find("link").text, pubdate=pubdate
        )

    return [parse_item(item) for item in tree.findall(".//item")]


_get_blog_feeds = cache.memcache_memoize(
    _get_blog_feeds, key_prefix="upstream.get_blog_feeds", timeout=5 * 60
)


def get_donation_include(include):
    web_input = web.input()

    # The following allows archive.org staff to test banners without
    # needing to reload openlibrary services:
    dev_host = web_input.pop("dev_host", "")  # e.g. `www-user`
    if dev_host and re.match('^[a-zA-Z0-9-.]+$', dev_host):
        script_src = "https://%s.archive.org/includes/donate.js" % dev_host
    else:
        script_src = "/cdn/archive.org/donate.js"

    if 'ymd' in web_input:
        script_src += '?ymd=' + web_input.ymd

    html = (
        """
    <div id="donato"></div>
    <script src="%s" data-platform="ol"></script>
    """
        % script_src
    )
    return html


# get_donation_include = cache.memcache_memoize(get_donation_include, key_prefix="upstream.get_donation_include", timeout=60)


@public
def item_image(image_path, default=None):
    if image_path is None:
        return default
    if image_path.startswith('https:'):
        return image_path
    return "https:" + image_path


@public
def get_blog_feeds():
    def process(post):
        post = web.storage(post)
        post.pubdate = parse_datetime(post.pubdate)
        return post

    return [process(post) for post in _get_blog_feeds()]


class Request:
    path = property(lambda self: web.ctx.path)
    home = property(lambda self: web.ctx.home)
    domain = property(lambda self: web.ctx.host)
    fullpath = property(lambda self: web.ctx.fullpath)

    @property
    def canonical_url(self):
        """Returns the https:// version of the URL.

        Used for adding <meta rel="canonical" ..> tag in all web pages.
        Required to make OL retain the page rank after https migration.
        """
        readable_path = web.ctx.get('readable_path', web.ctx.path) or ''
        query = web.ctx.query or ''
        host = web.ctx.host or ''
        url = host + readable_path + query
        if url:
            url = "https://" + url
            parsed_url = urlparse(url)

            parsed_query = parse_qs(parsed_url.query)
            queries_to_exclude = ['sort', 'mode', 'v', 'type', 'debug']

            canonical_query = {
                q: v for q, v in parsed_query.items() if q not in queries_to_exclude
            }
            query = parse_urlencode(canonical_query, doseq=True)
            parsed_url = parsed_url._replace(query=query)

            url = urlunparse(parsed_url)

            return url
        return ''


@public
def render_once(key):
    rendered = web.ctx.setdefault('render_once', {})
    if key in rendered:
        return False
    else:
        rendered[key] = True
        return True


@public
def today():
    return datetime.datetime.today()


class HTMLTagRemover(HTMLParser):
    def __init__(self):
        super().__init__()
        self.data = []

    def handle_data(self, data):
        self.data.append(data.strip())

    def handle_endtag(self, tag):
        self.data.append('\n' if tag in ('p', 'li') else ' ')


@public
def reformat_html(html_str: str, max_length: Optional[int] = None) -> str:
    """
    Reformats an HTML string, removing all opening and closing tags.
    Adds a line break element between each set of text content.
    Optionally truncates contents that exceeds the given max length.

    returns: A reformatted HTML string
    """
    parser = HTMLTagRemover()
    # Must have a root node, otherwise the parser will fail
    parser.feed(f'<div>{html_str}</div>')
    content = [web.websafe(s) for s in parser.data if s]

    if max_length:
        return truncate(''.join(content), max_length).strip().replace('\n', '<br>')
    else:
        return ''.join(content).strip().replace('\n', '<br>')


def setup():
    """Do required initialization"""
    # monkey-patch get_markdown to use OL Flavored Markdown
    view.get_markdown = get_markdown

    # Provide alternate implementations for websafe and commify
    web.websafe = websafe
    web.template.Template.FILTERS['.html'] = websafe
    web.template.Template.FILTERS['.xml'] = websafe

    web.commify = commify

    web.template.Template.globals.update(
        {
            'HTML': HTML,
            'request': Request(),
            'logger': logging.getLogger("openlibrary.template"),
            'sum': sum,
            'get_donation_include': get_donation_include,
            'websafe': web.websafe,
        }
    )

    from openlibrary.core import helpers as h

    web.template.Template.globals.update(h.helpers)

    if config.get('use_gzip') == True:
        config.middleware.append(GZipMiddleware)


if __name__ == '__main__':
    import doctest

    doctest.testmod()
