import datetime
import functools
import itertools
import json
import logging
import os
import re
import unicodedata
import urllib
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Callable, Generator, Iterable, Iterator, MutableMapping
from html import unescape
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Any, Literal, Protocol
from urllib.parse import (
    parse_qs,
    quote,
    quote_plus,
    urlparse,
    urlunparse,
)
from urllib.parse import urlencode as og_urlencode
from urllib.parse import (
    urlencode as parse_urlencode,
)

import babel
import babel.core
import babel.dates
import requests
import web
import yaml
from babel.lists import format_list
from web.template import TemplateResult
from web.utils import Storage

from infogami import config
from infogami.infobase.client import Changeset, Nothing, Thing, storify
from infogami.utils import delegate, features, stats, view
from infogami.utils.context import InfogamiContext, context
from infogami.utils.macro import macro
from infogami.utils.view import (
    get_template,
    public,
    render,
)
from openlibrary.core import cache
from openlibrary.core.helpers import commify, parse_datetime, truncate
from openlibrary.core.middleware import GZipMiddleware

if TYPE_CHECKING:
    from openlibrary.plugins.upstream.models import (
        Author,
        Edition,
        Work,
    )


STRIP_CHARS = ",'\" "
REPLACE_CHARS = "]["

logger = logging.getLogger('openlibrary')


class LanguageMultipleMatchError(Exception):
    """Exception raised when more than one possible language match is found."""

    def __init__(self, language_name):
        self.language_name = language_name


class LanguageNoMatchError(Exception):
    """Exception raised when no matching languages are found."""

    def __init__(self, language_name):
        self.language_name = language_name


class MultiDict(MutableMapping):
    """Ordered Dictionary that can store multiple values.

    Must be initialized without an `items` parameter, or `items` must be an
    iterable of two-value sequences. E.g., items=(('a', 1), ('b', 2))

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
    >>> d1 = MultiDict(items=(('a', 1), ('b', 2)), a=('x', 10, 11, 12))
    [('a', [1, ('x', 10, 11, 12)]), ('b', [2])]
    """

    def __init__(self, items: Iterable[tuple[Any, Any]] = (), **kw) -> None:
        self._items: list = []

        for k, v in items:
            self[k] = v
        self.update(kw)

    def __getitem__(self, key):
        if values := self.getall(key):
            return values[-1]
        else:
            raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
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
        return [k for k, _ in self._items]

    # Subclasses of MutableMapping should return a dictionary view object for
    # the values() method, but this implementation returns a list.
    # https://docs.python.org/3/library/stdtypes.html#dict-views
    def values(self) -> list[Any]:  # type: ignore[override]
        return [v for _, v in self._items]

    def items(self):
        return self._items[:]

    def multi_items(self) -> list[tuple[str, list]]:
        """Returns items as list of tuples of key and a list of values."""
        items = []
        d: dict = {}

        for k, v in self._items:
            if k not in d:
                d[k] = []
                items.append((k, d[k]))
            d[k].append(v)
        return items


@macro
@public
def render_template(name: str, *a, **kw) -> TemplateResult:
    if "." in name:
        name = name.rsplit(".", 1)[0]
    return render[name](*a, **kw)


def kebab_case(upper_camel_case: str) -> str:
    """
    :param str upper_camel_case: Text in upper camel case (e.g. "HelloWorld")
    :return: text in kebab case (e.g. 'hello-world')

    >>> kebab_case('HelloWorld')
    'hello-world'
    >>> kebab_case("MergeUI")
    'merge-ui'
    """
    # Match positions where a lowercase letter is followed by an uppercase letter,
    # or an uppercase letter is followed by another uppercase followed by a lowercase letter.
    kebab = re.sub(
        r'([a-z])([A-Z])', r'\1-\2', upper_camel_case
    )  # Handle camel case boundaries
    kebab = re.sub(r'([A-Z])([A-Z][a-z])', r'\1-\2', kebab)  # Handle acronyms
    return kebab.lower()


@public
def render_component(
    name: str,
    attrs: dict | None = None,
    json_encode: bool = True,
    asyncDefer=False,
) -> str:
    """
    :param str name: Name of the component (excluding extension)
    :param dict attrs: attributes to add to the component element
    """
    from openlibrary.plugins.upstream.code import static_url  # noqa: PLC0415

    attrs = attrs or {}
    attrs_str = ''
    for key, val in attrs.items():
        if (json_encode and isinstance(val, dict)) or isinstance(val, list):
            val = json.dumps(val)
            # On the Vue side use decodeURIComponent to decode
            val = urllib.parse.quote(val)
        attrs_str += f' {key}="{val}"'
    html = ''
    included = web.ctx.setdefault("included-components", [])

    if not included:
        # Support for legacy browsers (see vite.config.mjs)
        polyfills_url = static_url('build/components/production/ol-polyfills-legacy.js')
        html += f'<script nomodule src="{polyfills_url}" defer></script>'

    if name not in included:
        url = static_url('build/components/production/ol-%s.js' % name)
        script_attrs = '' if not asyncDefer else 'async defer'
        html += f'<script type="module" {script_attrs} src="{url}"></script>'

        legacy_url = static_url('build/components/production/ol-%s-legacy.js' % name)
        html += f'<script nomodule src="{legacy_url}" defer></script>'

        included.append(name)

    html += f'<ol-{kebab_case(name)} {attrs_str}></ol-{kebab_case(name)}>'
    return html


def render_macro(name, args, **kwargs):
    return dict(web.template.Template.globals['macros'][name](*args, **kwargs))


@public
def render_cached_macro(name: str, args: tuple, **kwargs):
    from openlibrary.plugins.openlibrary.code import is_bot  # noqa: PLC0415
    from openlibrary.plugins.openlibrary.home import caching_prethread  # noqa: PLC0415

    def get_key_prefix():
        lang = web.ctx.lang
        key_prefix = f'{name}.{lang}'
        cookies = web.cookies()
        if cookies.get('pd', False):
            key_prefix += '.pd'
        if cookies.get('sfw', ''):
            key_prefix += '.sfw'
        if is_bot():
            key_prefix += '.bot'
        return key_prefix

    five_minutes = 5 * 60
    key_prefix = get_key_prefix()
    mc = cache.memcache_memoize(
        render_macro,
        key_prefix=key_prefix,
        timeout=five_minutes,
        prethread=caching_prethread(),
        hash_args=True,  # this avoids cache key length overflow
    )

    try:
        page = mc(name, args, **kwargs)
        return web.template.TemplateResult(page)
    except (ValueError, TypeError):
        return '<span>Failed to render macro</span>'


@public
def get_error(name, *args):
    """Return error with the given name from errors.tmpl template."""
    return get_message_from_template("errors", name, args)


@public
def get_message(name: str, *args) -> str:
    """Return message with given name from messages.tmpl template"""
    return get_message_from_template("messages", name, args)


def get_message_from_template(
    template_name: str, name: str, args: tuple[(Any, ...)]
) -> str:
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
def commify_list(items: Iterable[Any]) -> str:
    # Not sure why lang is sometimes ''
    lang = web.ctx.lang or 'en'
    # If the list item is a template/html element, we strip it
    # so that there is no space before the comma.
    try:
        commified_list = format_list([str(x).strip() for x in items], locale=lang)
    except babel.UnknownLocaleError as e:
        logger.warning(f"unknown language for commify_list: {lang}. {e}")
        commified_list = format_list([str(x).strip() for x in items], locale="en")

    return commified_list


@public
def json_encode(d, indent=0) -> str:
    return json.dumps(d, indent=indent)


@public
def is_feature_enabled(feature_name: str) -> bool:
    return features.is_enabled(feature_name)


def unflatten(d: dict, separator: str = "--") -> dict:
    """Convert flattened data into nested form.

    >>> unflatten({"a": 1, "b--x": 2, "b--y": 3, "c--0": 4, "c--1": 5})
    {'a': 1, 'c': [4, 5], 'b': {'y': 3, 'x': 2}}
    >>> unflatten({"a--0--x": 1, "a--0--y": 2, "a--1--x": 3, "a--1--y": 4})
    {'a': [{'x': 1, 'y': 2}, {'x': 3, 'y': 4}]}

    """

    def isint(k: Any) -> bool:
        try:
            int(k)
            return True
        except ValueError:
            return False

    def setvalue(data: dict, k, v) -> None:
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
                return Storage((k, makelist(v)) for k, v in d.items())
        else:
            return d

    d2: dict = {}
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
def radio_input(checked=False, **params) -> str:
    params['type'] = 'radio'
    if checked:
        params['checked'] = "checked"
    return "<input %s />" % " ".join(
        [f'{k}="{web.websafe(v)}"' for k, v in params.items()]
    )


def get_coverstore_url() -> str:
    return config.get('coverstore_url', 'https://covers.openlibrary.org').rstrip('/')


@public
def get_coverstore_public_url() -> str:
    if OL_COVERSTORE_PUBLIC_URL := os.environ.get('OL_COVERSTORE_PUBLIC_URL'):
        return OL_COVERSTORE_PUBLIC_URL.rstrip('/')
    else:
        return config.get('coverstore_public_url', get_coverstore_url()).rstrip('/')


def _get_changes_v1_raw(
    query: dict[str, str | int], revision: int | None = None
) -> list[Storage]:
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
        # v.changes is not used and it contributes to memcache bloat in a big way.
        v.changes = '[]'

    return versions


def get_changes_v1(
    query: dict[str, str | int], revision: int | None = None
) -> list[Storage]:
    # uses the cached function _get_changes_v1_raw to get the raw data
    # and processes to before returning.
    def process(v):
        v = Storage(v)
        v.created = parse_datetime(v.created)
        v.author = v.author and web.ctx.site.get(v.author, lazy=True)
        return v

    return [process(v) for v in _get_changes_v1_raw(query, revision)]


def _get_changes_v2_raw(
    query: dict[str, str | int], revision: int | None = None
) -> list[dict]:
    """Returns the raw recentchanges response.

    Revision is taken as argument to make sure a new cache entry is used when a new revision of the page is created.
    """
    if 'env' not in web.ctx:
        delegate.fakeload()

    changes = web.ctx.site.recentchanges(query)
    return [c.dict() for c in changes]


# XXX-Anand: disabled temporarily to avoid too much memcache usage.
# _get_changes_v2_raw = cache.memcache_memoize(_get_changes_v2_raw, key_prefix="upstream._get_changes_v2_raw", timeout=10*60)


def get_changes_v2(
    query: dict[str, str | int], revision: int | None = None
) -> list[Changeset]:
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


def get_changes(
    query: dict[str, str | int], revision: int | None = None
) -> list[Changeset]:
    return get_changes_v2(query, revision=revision)


@public
def get_history(page: "Work | Author | Edition") -> Storage:
    h = Storage(
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
def get_recent_author(doc: "Work") -> "Thing | None":
    versions = get_changes_v1(
        {'key': doc.key, 'limit': 1, "offset": 0}, revision=doc.revision
    )
    if versions:
        return versions[0].author
    return None


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


class HasGetKeyRevision(Protocol):
    key: str
    revision: int

    def get(self, item) -> Any: ...


@public
def process_version(v: HasGetKeyRevision) -> HasGetKeyRevision:
    """Looks at the version and adds machine_comment required for showing "View MARC" link."""
    comments = [
        "found a matching marc record",
        "add publisher and source",
    ]

    if v.key.startswith('/books/') and not v.get('machine_comment'):
        thing = v.get('thing') or web.ctx.site.get(v.key, v.revision)
        if (thing.source_records and v.revision == 1) or (
            v.comment and v.comment.lower() in comments  # type: ignore [attr-defined]
        ):
            marc = thing.source_records[-1]
            if marc.startswith('marc:'):
                v.machine_comment = marc[len("marc:") :]  # type: ignore [attr-defined]
            else:
                v.machine_comment = marc  # type: ignore [attr-defined]
    return v


@public
def is_thing(t) -> bool:
    return isinstance(t, Thing)


@public
def putctx(key: str, value: str | bool) -> str:
    """Save a value in the context."""
    context[key] = value
    return ""


class Metatag:
    def __init__(self, tag: str = "meta", **attrs) -> None:
        self.tag = tag
        self.attrs = attrs

    def __str__(self) -> str:
        attrs = ' '.join(f'{k}="{websafe(v)}"' for k, v in self.attrs.items())
        return f'<{self.tag} {attrs} />'

    def __repr__(self) -> str:
        return 'Metatag(%s)' % str(self)


@public
def add_metatag(tag: str = "meta", **attrs) -> None:
    context.setdefault('metatags', [])
    context.metatags.append(Metatag(tag, **attrs))


@public
def url_quote(text: str | bytes) -> str:
    if isinstance(text, str):
        text = text.encode('utf8')
    return urllib.parse.quote_plus(text)


@public
def urlencode(dict_or_list_of_tuples: dict | list[tuple[str, Any]], plus=True) -> str:
    """
    You probably want to use this, if you're looking to urlencode parameters. This will
    encode things to utf8 that would otherwise cause urlencode to error.
    """

    tuples = dict_or_list_of_tuples
    if isinstance(dict_or_list_of_tuples, dict):
        tuples = list(dict_or_list_of_tuples.items())
    params = [(k, v.encode('utf-8') if isinstance(v, str) else v) for (k, v) in tuples]
    return og_urlencode(params, quote_via=quote_plus if plus else quote)


@public
def entity_decode(text: str) -> str:
    return unescape(text)


@public
def set_share_links(
    url: str = '#', title: str = '', view_context: InfogamiContext | None = None
) -> None:
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
    if view_context is not None:
        view_context.share_links = links


def safeget[T](func: Callable[[], T], default=None) -> T:
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
        return default


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
def get_languages(limit: int = 1000) -> dict:
    keys = web.ctx.site.things({"type": "/type/language", "limit": limit})
    return {
        lang.key: lang for lang in web.ctx.site.get_many(keys) if not lang.deprecated
    }


def word_prefix_match(prefix: str, text: str) -> bool:
    # Compare to each word of `text` for more accurate matching
    # Eg. the prefix 'greek' will match with 'ancient greek' as well as 'greek'
    return any(piece.startswith(prefix) for piece in text.split())


def autocomplete_languages(prefix: str) -> Iterator[Storage]:
    """
    Given, e.g., "English", this returns an iterator of the following:
        <Storage {'key': '/languages/ang', 'code': 'ang', 'name': 'English, Old (ca. 450-1100)'}>
        <Storage {'key': '/languages/cpe', 'code': 'cpe', 'name': 'Creoles and Pidgins, English-based (Other)'}>
        <Storage {'key': '/languages/eng', 'code': 'eng', 'name': 'English'}>
        <Storage {'key': '/languages/enm', 'code': 'enm', 'name': 'English, Middle (1100-1500)'}>
    """

    def get_names_to_try(lang: dict) -> Generator[str | None, None, None]:
        # For each language attempt to match based on:
        # The language's name translated into the current user's chosen language (user_lang)
        user_lang = web.ctx.lang or 'en'
        yield safeget(lambda: lang['name_translated'][user_lang][0])

        # The language's name translated into its native name (lang_iso_code)
        lang_iso_code = safeget(lambda: lang['identifiers']['iso_639_1'][0])
        yield safeget(lambda: lang['name_translated'][lang_iso_code][0])

        # The language's name as it was fetched from get_languages() (None)
        yield lang['name']

    def normalize_for_search(s: str) -> str:
        return strip_accents(s).lower()

    prefix = normalize_for_search(prefix)
    for lang in get_languages().values():
        for lang_name in get_names_to_try(lang):
            if lang_name and word_prefix_match(prefix, normalize_for_search(lang_name)):
                yield Storage(
                    key=lang.key,
                    code=lang.code,
                    name=lang_name,
                )
                break


def get_abbrev_from_full_lang_name(input_lang_name: str, languages=None) -> str:
    """
    Take a language name, in English, such as 'English' or 'French' and return
    'eng' or 'fre', respectively, if there is one match.

    If there are zero matches, raise LanguageNoMatchError.
    If there are multiple matches, raise a LanguageMultipleMatchError.
    """
    if languages is None:
        languages = get_languages().values()
    target_abbrev = ""

    def normalize(s: str) -> str:
        return strip_accents(s).lower()

    for language in languages:
        language_names = itertools.chain(
            (language.name,),
            (
                name
                for key in language.name_translated
                for name in language.name_translated[key]
            ),
        )

        for name in language_names:
            if normalize(name) == normalize(input_lang_name):
                if target_abbrev:
                    raise LanguageMultipleMatchError(input_lang_name)
                target_abbrev = language.code
                break

    if not target_abbrev:
        raise LanguageNoMatchError(input_lang_name)

    return target_abbrev


def get_language(lang_or_key: str) -> "None | Thing | Nothing":
    if isinstance(lang_or_key, str):
        return get_languages().get(lang_or_key)
    else:
        return lang_or_key


def get_marc21_language(language: str) -> str | None:
    """
    Get a three character MARC 21 language abbreviation from another abbreviation format:
        https://www.loc.gov/marc/languages/language_code.html
        https://www.loc.gov/standards/iso639-2/php/code_list.php

    Note: This does not contain all possible languages/abbreviations and is
    biased towards abbreviations in ISBNdb.
    """
    language_map = {
        'ab': 'abk',
        'af': 'afr',
        'afr': 'afr',
        'afrikaans': 'afr',
        'agq': 'agq',
        'ak': 'aka',
        'akk': 'akk',
        'alb': 'alb',
        'alg': 'alg',
        'am': 'amh',
        'amh': 'amh',
        'ang': 'ang',
        'apa': 'apa',
        'ar': 'ara',
        'ara': 'ara',
        'arabic': 'ara',
        'arc': 'arc',
        'arm': 'arm',
        'asa': 'asa',
        'aus': 'aus',
        'ave': 'ave',
        'az': 'aze',
        'aze': 'aze',
        'ba': 'bak',
        'baq': 'baq',
        'be': 'bel',
        'bel': 'bel',
        'bem': 'bem',
        'ben': 'ben',
        'bengali': 'ben',
        'bg': 'bul',
        'bis': 'bis',
        'bislama': 'bis',
        'bm': 'bam',
        'bn': 'ben',
        'bos': 'bos',
        'br': 'bre',
        'bre': 'bre',
        'breton': 'bre',
        'bul': 'bul',
        'bulgarian': 'bul',
        'bur': 'bur',
        'ca': 'cat',
        'cat': 'cat',
        'catalan': 'cat',
        'cau': 'cau',
        'cel': 'cel',
        'chi': 'chi',
        'chinese': 'chi',
        'chu': 'chu',
        'cop': 'cop',
        'cor': 'cor',
        'cos': 'cos',
        'cpe': 'cpe',
        'cpf': 'cpf',
        'cre': 'cre',
        'croatian': 'hrv',
        'crp': 'crp',
        'cs': 'cze',
        'cy': 'wel',
        'cze': 'cze',
        'czech': 'cze',
        'da': 'dan',
        'dan': 'dan',
        'danish': 'dan',
        'de': 'ger',
        'dut': 'dut',
        'dutch': 'dut',
        'dv': 'div',
        'dz': 'dzo',
        'ebu': 'ceb',
        'egy': 'egy',
        'el': 'gre',
        'en': 'eng',
        'en_us': 'eng',
        'enf': 'enm',
        'eng': 'eng',
        'english': 'eng',
        'enm': 'enm',
        'eo': 'epo',
        'epo': 'epo',
        'es': 'spa',
        'esk': 'esk',
        'esp': 'und',
        'est': 'est',
        'et': 'est',
        'eu': 'eus',
        'f': 'fre',
        'fa': 'per',
        'ff': 'ful',
        'fi': 'fin',
        'fij': 'fij',
        'filipino': 'fil',
        'fin': 'fin',
        'finnish': 'fin',
        'fle': 'fre',
        'fo': 'fao',
        'fon': 'fon',
        'fr': 'fre',
        'fra': 'fre',
        'fre': 'fre',
        'french': 'fre',
        'fri': 'fri',
        'frm': 'frm',
        'fro': 'fro',
        'fry': 'fry',
        'ful': 'ful',
        'ga': 'gae',
        'gae': 'gae',
        'gem': 'gem',
        'geo': 'geo',
        'ger': 'ger',
        'german': 'ger',
        'gez': 'gez',
        'gil': 'gil',
        'gl': 'glg',
        'gla': 'gla',
        'gle': 'gle',
        'glg': 'glg',
        'gmh': 'gmh',
        'grc': 'grc',
        'gre': 'gre',
        'greek': 'gre',
        'gsw': 'gsw',
        'guj': 'guj',
        'hat': 'hat',
        'hau': 'hau',
        'haw': 'haw',
        'heb': 'heb',
        'hebrew': 'heb',
        'her': 'her',
        'hi': 'hin',
        'hin': 'hin',
        'hindi': 'hin',
        'hmn': 'hmn',
        'hr': 'hrv',
        'hrv': 'hrv',
        'hu': 'hun',
        'hun': 'hun',
        'hy': 'hye',
        'ice': 'ice',
        'id': 'ind',
        'iku': 'iku',
        'in': 'ind',
        'ind': 'ind',
        'indonesian': 'ind',
        'ine': 'ine',
        'ira': 'ira',
        'iri': 'iri',
        'irish': 'iri',
        'is': 'ice',
        'it': 'ita',
        'ita': 'ita',
        'italian': 'ita',
        'iw': 'heb',
        'ja': 'jpn',
        'jap': 'jpn',
        'japanese': 'jpn',
        'jpn': 'jpn',
        'ka': 'kat',
        'kab': 'kab',
        'khi': 'khi',
        'khm': 'khm',
        'kin': 'kin',
        'kk': 'kaz',
        'km': 'khm',
        'ko': 'kor',
        'kon': 'kon',
        'kor': 'kor',
        'korean': 'kor',
        'kur': 'kur',
        'ky': 'kir',
        'la': 'lat',
        'lad': 'lad',
        'lan': 'und',
        'lat': 'lat',
        'latin': 'lat',
        'lav': 'lav',
        'lcc': 'und',
        'lit': 'lit',
        'lo': 'lao',
        'lt': 'ltz',
        'ltz': 'ltz',
        'lv': 'lav',
        'mac': 'mac',
        'mal': 'mal',
        'mao': 'mao',
        'map': 'map',
        'mar': 'mar',
        'may': 'may',
        'mfe': 'mfe',
        'mic': 'mic',
        'mis': 'mis',
        'mk': 'mkh',
        'ml': 'mal',
        'mla': 'mla',
        'mlg': 'mlg',
        'mlt': 'mlt',
        'mn': 'mon',
        'moh': 'moh',
        'mon': 'mon',
        'mr': 'mar',
        'ms': 'msa',
        'mt': 'mlt',
        'mul': 'mul',
        'my': 'bur',
        'mya': 'bur',
        'burmese': 'bur',
        'myn': 'myn',
        'nai': 'nai',
        'nav': 'nav',
        'nde': 'nde',
        'ndo': 'ndo',
        'ne': 'nep',
        'nep': 'nep',
        'nic': 'nic',
        'nl': 'dut',
        'nor': 'nor',
        'norwegian': 'nor',
        'nso': 'sot',
        'ny': 'nya',
        'oc': 'oci',
        'oci': 'oci',
        'oji': 'oji',
        'old norse': 'non',
        'opy': 'und',
        'ori': 'ori',
        'ota': 'ota',
        'paa': 'paa',
        'pal': 'pal',
        'pan': 'pan',
        'per': 'per',
        'persian': 'per',
        'farsi': 'per',
        'pl': 'pol',
        'pli': 'pli',
        'pol': 'pol',
        'polish': 'pol',
        'por': 'por',
        'portuguese': 'por',
        'pra': 'pra',
        'pro': 'pro',
        'ps': 'pus',
        'pt': 'por',
        'pt-br': 'por',
        'que': 'que',
        'ro': 'rum',
        'roa': 'roa',
        'roh': 'roh',
        'romanian': 'rum',
        'ru': 'rus',
        'rum': 'rum',
        'rus': 'rus',
        'russian': 'rus',
        'rw': 'kin',
        'sai': 'sai',
        'san': 'san',
        'scc': 'srp',
        'sco': 'sco',
        'scottish gaelic': 'gla',
        'scr': 'scr',
        'sesotho': 'sot',
        'sho': 'sna',
        'shona': 'sna',
        'si': 'sin',
        'sl': 'slv',
        'sla': 'sla',
        'slo': 'slv',
        'slovenian': 'slv',
        'slv': 'slv',
        'smo': 'smo',
        'sna': 'sna',
        'som': 'som',
        'sot': 'sot',
        'sotho': 'sot',
        'spa': 'spa',
        'spanish': 'spa',
        'sq': 'alb',
        'sr': 'srp',
        'srp': 'srp',
        'srr': 'srr',
        'sso': 'sso',
        'ssw': 'ssw',
        'st': 'sot',
        'sux': 'sux',
        'sv': 'swe',
        'sw': 'swa',
        'swa': 'swa',
        'swahili': 'swa',
        'swe': 'swe',
        'swedish': 'swe',
        'swz': 'ssw',
        'syc': 'syc',
        'syr': 'syr',
        'ta': 'tam',
        'tag': 'tgl',
        'tah': 'tah',
        'tam': 'tam',
        'tel': 'tel',
        'tg': 'tgk',
        'tgl': 'tgl',
        'th': 'tha',
        'tha': 'tha',
        'tib': 'tib',
        'tl': 'tgl',
        'tr': 'tur',
        'tsn': 'tsn',
        'tso': 'sot',
        'tsonga': 'tsonga',
        'tsw': 'tsw',
        'tswana': 'tsw',
        'tur': 'tur',
        'turkish': 'tur',
        'tut': 'tut',
        'uk': 'ukr',
        'ukr': 'ukr',
        'un': 'und',
        'und': 'und',
        'urd': 'urd',
        'urdu': 'urd',
        'uz': 'uzb',
        'uzb': 'uzb',
        'ven': 'ven',
        'vi': 'vie',
        'vie': 'vie',
        'wel': 'wel',
        'welsh': 'wel',
        'wen': 'wen',
        'wol': 'wol',
        'xho': 'xho',
        'xhosa': 'xho',
        'yid': 'yid',
        'yor': 'yor',
        'yu': 'ypk',
        'zh': 'chi',
        'zh-cn': 'chi',
        'zh-tw': 'chi',
        'zul': 'zul',
        'zulu': 'zul',
    }
    return language_map.get(language.casefold())


@public
def get_language_name(lang_or_key: "Nothing | str | Thing") -> Nothing | str:
    if isinstance(lang_or_key, str):
        lang = get_language(lang_or_key)
        if not lang:
            return lang_or_key
    else:
        lang = lang_or_key

    user_lang = web.ctx.lang or 'en'
    return safeget(lambda: lang['name_translated'][user_lang][0]) or lang.name  # type: ignore[index]


@public
def get_populated_languages() -> set[str]:
    """
    Get the languages for which we have many available ebooks, in MARC21 format
    See https://openlibrary.org/languages
    """
    # Hard-coded for now to languages with more than 15k borrowable ebooks
    return {'eng', 'fre', 'ger', 'spa', 'chi', 'ita', 'lat', 'dut', 'rus', 'jpn'}


@public
@functools.cache
def convert_iso_to_marc(iso_639_1: str) -> str | None:
    """
    e.g. 'en' -> 'eng'
    """
    for lang in get_languages().values():
        code = safeget(lambda: lang['identifiers']['iso_639_1'][0])
        if code == iso_639_1:
            return lang.code
    return None


@public
def get_identifier_config(identifier: Literal['work', 'edition', 'author']) -> Storage:
    return _get_identifier_config(identifier)


@web.memoize
def _get_identifier_config(identifier: Literal['work', 'edition', 'author']) -> Storage:
    """
    Returns the identifier config.

    The results are cached on the first invocation. Any changes to /config/{identifier} page require restarting the app.

    This is cached because fetching and creating the Thing object was taking about 20ms of time for each book request.
    """
    with open(
        f'openlibrary/plugins/openlibrary/config/{identifier}/identifiers.yml'
    ) as in_file:
        id_config = yaml.safe_load(in_file)
        identifiers = [
            Storage(id) for id in id_config.get('identifiers', []) if 'name' in id
        ]

    if identifier == 'edition':
        thing = web.ctx.site.get('/config/edition')
        classifications = [
            Storage(t.dict()) for t in thing.classifications if 'name' in t
        ]
        roles = thing.roles
        return Storage(
            classifications=classifications, identifiers=identifiers, roles=roles
        )

    return Storage(identifiers=identifiers)


from openlibrary.core.olmarkdown import OLMarkdown


def get_markdown(text: str, safe_mode: bool = False) -> OLMarkdown:
    md = OLMarkdown(source=text, safe_mode=safe_mode)
    view._register_mdx_extensions(md)
    md.postprocessors += view.wiki_processors
    return md


class HTML(str):
    __slots__ = ()

    def __init__(self, html):
        str.__init__(self, web.safeunicode(html))

    def __repr__(self):
        return "<html: %s>" % str.__repr__(self)


_websafe = web.websafe


def websafe(text: str) -> str:
    if isinstance(text, HTML):
        return text
    elif isinstance(text, TemplateResult):
        return web.safestr(text)
    else:
        return _websafe(text)


import memcache

from openlibrary.plugins.upstream import adapter
from openlibrary.utils import olmemcache
from openlibrary.utils.olcompress import OLCompressor


class UpstreamMemcacheClient:
    """Wrapper to memcache Client to handle upstream specific conversion and OL specific compression.
    Compatible with memcache Client API.
    """

    def __init__(self, servers):
        self._client = memcache.Client(servers)
        compressor = OLCompressor()
        self.compress = compressor.compress

        def decompress(*args, **kw) -> str:
            d = json.loads(compressor.decompress(*args, **kw))
            return json.dumps(adapter.unconvert_dict(d))

        self.decompress = decompress

    def get(self, key: str | None):
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
        t = Storage()
        for k in ["key", "title", "name", "displayname"]:
            t[k] = thing[k]
        t['type'] = Storage(key=thing.type.key)
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
def _get_blog_feeds():
    url = "https://blog.openlibrary.org/feed/"
    try:
        stats.begin("get_blog_feeds", url=url)
        tree = ET.fromstring(requests.get(url).text)
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
        return {
            "title": item.find("title").text,
            "link": item.find("link").text,
            "pubdate": pubdate,
        }

    return [parse_item(item) for item in tree.findall(".//item")]


_get_blog_feeds = cache.memcache_memoize(
    _get_blog_feeds, key_prefix="upstream.get_blog_feeds", timeout=5 * 60
)


@public
def is_jsdef():
    return False


@public
def jsdef_get(obj, key, default=None):
    """
    foo.get(KEY, default) isn't defined in js, so we can't use that construct
    in our jsdef methods. This helper function provides a workaround, and works
    in both environments.
    """
    return obj.get(key, default)


@public
def get_ia_host(allow_dev: bool = False) -> str:
    if allow_dev:
        web_input = web.input()
        dev_host = web_input.pop("dev_host", "")  # e.g. `www-user`
        if dev_host and re.match('^[a-zA-Z0-9-.]+$', dev_host):
            return dev_host + ".archive.org"

    return "archive.org"


@public
def item_image(image_path: str | None, default: str | None = None) -> str | None:
    if image_path is None:
        return default
    if image_path.startswith('https:'):
        return image_path
    return "https:" + image_path


@public
def get_blog_feeds() -> list[Storage]:
    def process(post):
        post = Storage(post)
        post.pubdate = parse_datetime(post.pubdate)
        return post

    return [process(post) for post in _get_blog_feeds()]


class Request:
    path = property(lambda self: web.ctx.path)
    home = property(lambda self: web.ctx.home)
    domain = property(lambda self: web.ctx.host)
    fullpath = property(lambda self: web.ctx.fullpath)

    @property
    def canonical_url(self) -> str:
        """Returns the https:// version of the URL.

        Used for adding <meta rel="canonical" ..> tag in all web pages.
        Required to make OL retain the page rank after https migration.
        """
        readable_path = web.ctx.get('readable_path', web.ctx.path) or ''
        query = web.ctx.query or ''
        host = web.ctx.host or ''
        if url := host + readable_path + query:
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
def render_once(key: str) -> bool:
    rendered = web.ctx.setdefault('render_once', {})
    if key in rendered:
        return False
    else:
        rendered[key] = True
        return True


@public
def today():
    return datetime.datetime.today()


@public
def to_datetime(time: str):
    return datetime.datetime.fromisoformat(time)


class HTMLTagRemover(HTMLParser):
    def __init__(self):
        super().__init__()
        self.data = []

    def handle_data(self, data):
        self.data.append(data.strip())

    def handle_endtag(self, tag):
        self.data.append('\n' if tag in ('p', 'li') else ' ')


@public
def get_user_object(username):
    user = web.ctx.site.get(f'/people/{username}')
    return user


@public
def reformat_html(html_str: str, max_length: int | None = None) -> str:
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


def get_colon_only_loc_pub(pair: str) -> tuple[str, str]:
    """
    Get a tuple of a location and publisher name from an Internet Archive
    publisher string. For use in simple location-publisher pairs with one colon.

    >>> get_colon_only_loc_pub('City : Publisher Name')
    ('City', 'Publisher Name')
    """
    pairs = pair.split(":")
    if len(pairs) == 2:
        location = pairs[0].strip(STRIP_CHARS)
        publisher = pairs[1].strip(STRIP_CHARS)

        return (location, publisher)

    # Fall back to using the entire string as the publisher.
    return ("", pair.strip(STRIP_CHARS))


def get_location_and_publisher(loc_pub: str) -> tuple[list[str], list[str]]:
    """
    Parses locations and publisher names out of Internet Archive metadata
    `publisher` strings. For use when there is no MARC record.

    Returns a tuple of list[location_strings], list[publisher_strings].

    E.g.
    >>> get_location_and_publisher("[New York] : Random House")
    (['New York'], ['Random House'])
    >>> get_location_and_publisher("Londres ; New York ; Paris : Berlitz Publishing")
    (['Londres', 'New York', 'Paris'], ['Berlitz Publishing'])
    >>> get_location_and_publisher("Paris : Pearson ; San Jose (Calif.) : Adobe")
    (['Paris', 'San Jose (Calif.)'], ['Pearson', 'Adobe'])
    """

    if not loc_pub or not isinstance(loc_pub, str):
        return ([], [])

    if "Place of publication not identified" in loc_pub:
        loc_pub = loc_pub.replace("Place of publication not identified", "")

    loc_pub = loc_pub.translate({ord(char): None for char in REPLACE_CHARS})

    # This operates on the notion that anything, even multiple items, to the
    # left of a colon is a location, and the item immediately to the right of
    # the colon is a publisher. This can be exploited by using
    # string.split(";") because everything to the 'left' of a colon is a
    # location, and whatever is to the right is a publisher.
    if ":" in loc_pub:
        locations: list[str] = []
        publishers: list[str] = []
        parts = loc_pub.split(";") if ";" in loc_pub else [loc_pub]
        # Track in indices of values placed into locations or publishers.
        last_placed_index = 0

        # For each part, look for a semi-colon, then extract everything to
        # the left as a location, and the item on the right as a publisher.
        for index, part in enumerate(parts):
            # This expects one colon per part. Two colons breaks our pattern.
            # Breaking here gives the chance of extracting a
            # `location : publisher` from one or more pairs with one semi-colon.
            if part.count(":") > 1:
                break

            # Per the pattern, anything "left" of a colon in a part is a place.
            if ":" in part:
                location, publisher = get_colon_only_loc_pub(part)
                publishers.append(publisher)
                # Every index value between last_placed_index and the current
                # index is a location.
                for place in parts[last_placed_index:index]:
                    locations.append(place.strip(STRIP_CHARS))
                locations.append(location)  # Preserve location order.
                last_placed_index = index + 1

        # Clean up and empty list items left over from strip() string replacement.
        locations = [item for item in locations if item]
        publishers = [item for item in publishers if item]

        return (locations, publishers)

    # Fall back to making the input a list returning that and an empty location.
    return ([], [loc_pub.strip(STRIP_CHARS)])


def setup_requests(config=config) -> None:
    logger.info("Setting up requests")

    logger.info("Setting up proxy")
    if config.get("http_proxy", ""):
        os.environ['HTTP_PROXY'] = os.environ['http_proxy'] = config.get('http_proxy')
        os.environ['HTTPS_PROXY'] = os.environ['https_proxy'] = config.get('http_proxy')
        logger.info('Proxy environment variables are set')
    else:
        logger.info("No proxy configuration found")

    logger.info("Setting up proxy bypass")
    if config.get("no_proxy_addresses", []):
        no_proxy = ",".join(config.get("no_proxy_addresses"))
        os.environ['NO_PROXY'] = os.environ['no_proxy'] = no_proxy
        logger.info('Proxy bypass environment variables are set')
    else:
        logger.info("No proxy bypass configuration found")

    logger.info("Requests set up")


def setup() -> None:
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
            'websafe': web.websafe,
        }
    )

    from openlibrary.core import helpers as h  # noqa: PLC0415

    web.template.Template.globals.update(h.helpers)

    if config.get('use_gzip') is True:
        config.middleware.append(GZipMiddleware)


if __name__ == '__main__':
    import doctest

    doctest.testmod()
