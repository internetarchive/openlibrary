"""
Open Library Plugin.
"""

import requests
import web
import json
import os
import socket
import random
import datetime
import logging
from time import time
import math

import infogami

# make sure infogami.config.features is set
if not hasattr(infogami.config, 'features'):
    infogami.config.features = []  # type: ignore[attr-defined]

from infogami.utils.app import metapage
from infogami.utils import delegate
from openlibrary.utils import dateutil
from infogami.utils.view import (
    render,
    render_template,
    public,
    safeint,
    add_flash_message,
)
from infogami.infobase import client
from infogami.core.db import ValidationException

from openlibrary.core import cache
from openlibrary.core.vendors import create_edition_from_amazon_metadata
from openlibrary.utils.isbn import isbn_13_to_isbn_10, isbn_10_to_isbn_13
from openlibrary.core.models import Edition  # noqa: E402
from openlibrary.core.lending import get_work_availability, get_edition_availability
import openlibrary.core.stats
from openlibrary.plugins.openlibrary.home import format_work_data
from openlibrary.plugins.openlibrary.stats import increment_error_count  # noqa: E402
from openlibrary.plugins.openlibrary import processors

delegate.app.add_processor(processors.ReadableUrlProcessor())
delegate.app.add_processor(processors.ProfileProcessor())
delegate.app.add_processor(processors.CORSProcessor(cors_prefixes={'/api/'}))

try:
    from infogami.plugins.api import code as api
except:
    api = None  # type: ignore[assignment]

# http header extension for OL API
infogami.config.http_ext_header_uri = 'http://openlibrary.org/dev/docs/api'  # type: ignore[attr-defined]

# setup special connection with caching support
from openlibrary.plugins.openlibrary import connection

client._connection_types['ol'] = connection.OLConnection  # type: ignore[assignment]
infogami.config.infobase_parameters = dict(type='ol')

# set up infobase schema. required when running in standalone mode.
from openlibrary.core import schema

schema.register_schema()

from openlibrary.core import models

models.register_models()
models.register_types()

# Remove movefiles install hook. openlibrary manages its own files.
infogami._install_hooks = [
    h for h in infogami._install_hooks if h.__name__ != 'movefiles'
]

from openlibrary.plugins.openlibrary import lists

lists.setup()

logger = logging.getLogger('openlibrary')


class hooks(client.hook):
    def before_new_version(self, page):
        user = web.ctx.site.get_user()
        account = user and user.get_account()
        if account and account.is_blocked():
            raise ValidationException(
                'Your account has been suspended. You are not allowed to make any edits.'
            )

        if page.key.startswith('/a/') or page.key.startswith('/authors/'):
            if page.type.key == '/type/author':
                return

            books = web.ctx.site.things({'type': '/type/edition', 'authors': page.key})
            books = books or web.ctx.site.things(
                {'type': '/type/work', 'authors': {'author': {'key': page.key}}}
            )
            if page.type.key == '/type/delete' and books:
                raise ValidationException(
                    'This Author page cannot be deleted as %d record(s) still reference this id. Please remove or reassign before trying again. Referenced by: %s'
                    % (len(books), books)
                )
            elif page.type.key != '/type/author' and books:
                raise ValidationException(
                    'Changing type of author pages is not allowed.'
                )


@infogami.action
def sampledump():
    """Creates a dump of objects from OL database for creating a sample database."""

    def expand_keys(keys):
        def f(k):
            if isinstance(k, dict):
                return web.ctx.site.things(k)
            elif k.endswith('*'):
                return web.ctx.site.things({'key~': k})
            else:
                return [k]

        result = []
        for k in keys:
            d = f(k)
            result += d
        return result

    def get_references(data, result=None):
        if result is None:
            result = []

        if isinstance(data, dict):
            if 'key' in data:
                result.append(data['key'])
            else:
                get_references(data.values(), result)
        elif isinstance(data, list):
            for v in data:
                get_references(v, result)
        return result

    visiting = {}
    visited = set()

    def visit(key):
        if key in visited or key.startswith('/type/'):
            return
        elif key in visiting:
            # This is a case of circular-dependency. Add a stub object to break it.
            print(json.dumps({'key': key, 'type': visiting[key]['type']}))
            visited.add(key)
            return

        thing = web.ctx.site.get(key)
        if not thing:
            return

        d = thing.dict()
        d.pop('permission', None)
        d.pop('child_permission', None)
        d.pop('table_of_contents', None)

        visiting[key] = d
        for ref in get_references(d.values()):
            visit(ref)
        visited.add(key)

        print(json.dumps(d))

    keys = [
        '/scan_record',
        '/scanning_center',
        {'type': '/type/scan_record', 'limit': 10},
    ]
    keys = expand_keys(keys) + ['/b/OL%dM' % i for i in range(1, 100)]
    visited = set()

    for k in keys:
        visit(k)


@infogami.action
def sampleload(filename='sampledump.txt.gz'):
    if filename.endswith('.gz'):
        import gzip

        f = gzip.open(filename)
    else:
        f = open(filename)

    queries = [json.loads(line) for line in f]
    print(web.ctx.site.save_many(queries))


class routes(delegate.page):
    path = '/developers/routes'

    def GET(self):
        class ModulesToStr(json.JSONEncoder):
            def default(self, obj):
                if isinstance(obj, metapage):
                    return obj.__module__ + '.' + obj.__name__
                return super().default(obj)

        from openlibrary import code

        return '<pre>%s</pre>' % json.dumps(
            code.delegate.pages,
            sort_keys=True,
            cls=ModulesToStr,
            indent=4,
            separators=(',', ': '),
        )


class addbook(delegate.page):
    path = '/addbook'

    def GET(self):
        d = {'type': web.ctx.site.get('/type/edition')}

        i = web.input()
        author = i.get('author') and web.ctx.site.get(i.author)
        if author:
            d['authors'] = [author]

        page = web.ctx.site.new("", d)
        return render.edit(page, self.path, 'Add Book')

    def POST(self):
        from infogami.core.code import edit

        key = web.ctx.site.new_key('/type/edition')
        web.ctx.path = key
        return edit().POST(key)


class widget(delegate.page):
    path = r'/(works|books)/(OL\d+[W|M])/widget'

    def GET(self, _type, olid=None):
        if olid:
            getter = (
                get_work_availability if _type == 'works' else get_edition_availability
            )
            item = web.ctx.site.get(f'/{_type}/{olid}') or {}
            item['olid'] = olid
            item['availability'] = getter(olid).get(item['olid'])
            item['authors'] = [
                web.storage(key=a.key, name=a.name or None) for a in item.get_authors()
            ]
            return delegate.RawText(
                render_template(
                    'widget', item if _type == 'books' else format_work_data(item)
                ),
                content_type='text/html',
            )
        raise web.seeother('/')


class addauthor(delegate.page):
    path = '/addauthor'

    def POST(self):
        i = web.input('name')
        if len(i.name) < 2:
            return web.badrequest()
        key = web.ctx.site.new_key('/type/author')
        web.ctx.path = key
        web.ctx.site.save(
            {'key': key, 'name': i.name, 'type': dict(key='/type/author')},
            comment='New Author',
        )
        raise web.HTTPError('200 OK', {}, key)


class clonebook(delegate.page):
    def GET(self):
        from infogami.core.code import edit

        i = web.input('key')
        page = web.ctx.site.get(i.key)
        if page is None:
            raise web.seeother(i.key)
        else:
            d = page._getdata()
            for k in ['isbn_10', 'isbn_13', 'lccn', 'oclc']:
                d.pop(k, None)
            return render.edit(page, '/addbook', 'Clone Book')


class search(delegate.page):
    path = '/suggest/search'

    def GET(self):
        i = web.input(prefix='')
        if len(i.prefix) > 2:
            q = {
                'type': '/type/author',
                'name~': i.prefix + '*',
                'sort': 'name',
                'limit': 5,
            }
            things = web.ctx.site.things(q)
            things = [web.ctx.site.get(key) for key in things]
            result = [
                dict(
                    type=[{'id': t.key, 'name': t.key}],
                    name=web.safestr(t.name),
                    guid=t.key,
                    id=t.key,
                    article=dict(id=t.key),
                )
                for t in things
            ]
        else:
            result = []
        callback = i.pop('callback', None)
        d = dict(
            status='200 OK',
            query=dict(i, escape='html'),
            code='/api/status/ok',
            result=result,
        )

        if callback:
            data = f'{callback}({json.dumps(d)})'
        else:
            data = json.dumps(d)
        raise web.HTTPError('200 OK', {}, data)


class blurb(delegate.page):
    path = '/suggest/blurb/(.*)'

    def GET(self, path):
        i = web.input()
        callback = i.pop('callback', None)
        author = web.ctx.site.get('/' + path)
        body = ''
        if author.birth_date or author.death_date:
            body = f'{author.birth_date} - {author.death_date}'
        else:
            body = '%s' % author.date

        body += '<br/>'
        if author.bio:
            body += web.safestr(author.bio)

        result = dict(body=body, media_type='text/html', text_encoding='utf-8')
        d = dict(status='200 OK', code='/api/status/ok', result=result)
        if callback:
            data = f'{callback}({json.dumps(d)})'
        else:
            data = json.dumps(d)

        raise web.HTTPError('200 OK', {}, data)


class thumbnail(delegate.page):
    path = '/suggest/thumbnail'


@public
def get_property_type(type, name):
    for p in type.properties:
        if p.name == name:
            return p.expected_type
    return web.ctx.site.get('/type/string')


def save(filename, text):
    root = os.path.dirname(__file__)
    path = root + filename
    dir = os.path.dirname(path)
    if not os.path.exists(dir):
        os.makedirs(dir)
    f = open(path, 'w')
    f.write(text)
    f.close()


def change_ext(filename, ext):
    filename, _ = os.path.splitext(filename)
    if ext:
        filename = filename + ext
    return filename


def get_pages(type, processor):
    pages = web.ctx.site.things(dict(type=type))
    for p in pages:
        processor(web.ctx.site.get(p))


class robotstxt(delegate.page):
    path = '/robots.txt'

    def GET(self):
        web.header('Content-Type', 'text/plain')
        try:
            is_dev = (
                'dev' in infogami.config.features or web.ctx.host != 'openlibrary.org'
            )
            robots_file = 'norobots.txt' if is_dev else 'robots.txt'
            data = open('static/' + robots_file).read()
            raise web.HTTPError('200 OK', {}, data)
        except OSError:
            raise web.notfound()


@web.memoize
def fetch_ia_js(filename: str) -> str:
    return requests.get(f'https://archive.org/includes/{filename}').text


class ia_js_cdn(delegate.page):
    path = r'/cdn/archive.org/(donate\.js|analytics\.js)'

    def GET(self, filename):
        web.header('Content-Type', 'text/javascript')
        raise web.HTTPError('200 OK', {}, fetch_ia_js(filename))


class serviceworker(delegate.page):
    path = '/sw.js'

    def GET(self):
        web.header('Content-Type', 'text/javascript')
        try:
            data = open('static/build/sw.js').read()
            raise web.HTTPError('200 OK', {}, data)
        except OSError:
            raise web.notfound()


class assetlinks(delegate.page):
    """To verify the TWA, currently serves dummy data"""

    path = '/.well-known/assetlinks'

    def GET(self):
        web.header('Content-Type', 'application/json')
        try:
            data = open('static/.well-known/assetlinks.json').read()
            raise web.HTTPError('200 OK', {}, data)
        except OSError:
            raise web.notfound()


class opensearchxml(delegate.page):
    path = '/opensearch.xml'

    def GET(self):
        web.header('Content-Type', 'text/plain')
        try:
            data = open('static/opensearch.xml').read()
            raise web.HTTPError('200 OK', {}, data)
        except OSError:
            raise web.notfound()


class health(delegate.page):
    path = '/health'

    def GET(self):
        web.header('Content-Type', 'text/plain')
        raise web.HTTPError('200 OK', {}, 'OK')


class isbn_lookup(delegate.page):

    path = r'/(?:isbn|ISBN)/([0-9xX-]+)'

    def GET(self, isbn):
        # Preserve the url type (e.g. `.json`) and query params
        ext = ''
        if web.ctx.encoding and web.ctx.path.endswith('.' + web.ctx.encoding):
            ext = '.' + web.ctx.encoding
        if web.ctx.env.get('QUERY_STRING'):
            ext += '?' + web.ctx.env['QUERY_STRING']

        try:
            ed = Edition.from_isbn(isbn)
            if ed:
                return web.found(ed.key + ext)
        except Exception as e:
            logger.error(e)
            return repr(e)

        web.ctx.status = '404 Not Found'
        return render.notfound(web.ctx.path, create=False)


class bookpage(delegate.page):
    """
    Load an edition bookpage by identifier: isbn, oclc, lccn, or ia (ocaid).
    otherwise, return a 404.
    """

    path = r'/(oclc|lccn|ia|OCLC|LCCN|IA)/([^/]*)(/.*)?'

    def GET(self, key, value, suffix=''):
        key = key.lower()

        if key == 'oclc':
            key = 'oclc_numbers'
        elif key == 'ia':
            key = 'ocaid'

        if key != 'ocaid':  # example: MN41558ucmf_6
            value = value.replace('_', ' ')

        if web.ctx.encoding and web.ctx.path.endswith('.' + web.ctx.encoding):
            ext = '.' + web.ctx.encoding
        else:
            ext = ''

        if web.ctx.env.get('QUERY_STRING'):
            ext += '?' + web.ctx.env['QUERY_STRING']

        q = {'type': '/type/edition', key: value}

        result = web.ctx.site.things(q)

        if result:
            return web.found(result[0] + ext)
        elif key == 'ocaid':
            # Try a range of ocaid alternatives:
            ocaid_alternatives = [
                {'type': '/type/edition', 'source_records': 'ia:' + value},
                {'type': '/type/volume', 'ia_id': value},
            ]
            for q in ocaid_alternatives:
                result = web.ctx.site.things(q)
                if result:
                    return web.found(result[0] + ext)

            # Perform import, if possible
            from openlibrary.plugins.importapi.code import ia_importapi, BookImportError
            from openlibrary import accounts

            with accounts.RunAs('ImportBot'):
                try:
                    ia_importapi.ia_import(value, require_marc=True)
                except BookImportError:
                    logger.exception('Unable to import ia record')

            # Go the the record created, or to the dummy ia-wrapper record
            return web.found('/books/ia:' + value + ext)

        web.ctx.status = '404 Not Found'
        return render.notfound(web.ctx.path, create=False)


delegate.media_types['application/rdf+xml'] = 'rdf'


class rdf(delegate.mode):
    name = 'view'
    encoding = 'rdf'

    def GET(self, key):
        page = web.ctx.site.get(key)
        if not page:
            raise web.notfound('')
        else:
            from infogami.utils import template

            try:
                result = template.typetemplate('rdf')(page)
            except:
                raise web.notfound('')
            else:
                return delegate.RawText(
                    result, content_type='application/rdf+xml; charset=utf-8'
                )


delegate.media_types[' application/atom+xml;profile=opds'] = 'opds'


class opds(delegate.mode):
    name = 'view'
    encoding = 'opds'

    def GET(self, key):
        page = web.ctx.site.get(key)
        if not page:
            raise web.notfound('')
        else:
            from openlibrary.plugins.openlibrary import opds
            try:
                result = opds.OPDSEntry(page).to_string()
            except:
                raise web.notfound('')
            else:
                return delegate.RawText(
                    result, content_type=' application/atom+xml;profile=opds'
                )


delegate.media_types['application/marcxml+xml'] = 'marcxml'


class marcxml(delegate.mode):
    name = 'view'
    encoding = 'marcxml'

    def GET(self, key):
        page = web.ctx.site.get(key)
        if page is None or page.type.key != '/type/edition':
            raise web.notfound('')
        else:
            from infogami.utils import template

            try:
                result = template.typetemplate('marcxml')(page)
            except:
                raise web.notfound('')
            else:
                return delegate.RawText(
                    result, content_type='application/marcxml+xml; charset=utf-8'
                )


delegate.media_types['text/x-yaml'] = 'yml'


class _yaml(delegate.mode):
    name = 'view'
    encoding = 'yml'

    def GET(self, key):
        d = self.get_data(key)

        if web.input(text='false').text.lower() == 'true':
            web.header('Content-Type', 'text/plain; charset=utf-8')
        else:
            web.header('Content-Type', 'text/x-yaml; charset=utf-8')

        raise web.ok(self.dump(d))

    def get_data(self, key):
        i = web.input(v=None)
        v = safeint(i.v, None)
        data = dict(key=key, revision=v)
        try:
            d = api.request('/get', data=data)
        except client.ClientException as e:
            if e.json:
                msg = self.dump(json.loads(e.json))
            else:
                msg = str(e)
            raise web.HTTPError(e.status, data=msg)

        return json.loads(d)

    def dump(self, d):
        import yaml

        return yaml.safe_dump(d, indent=4, allow_unicode=True, default_flow_style=False)

    def load(self, data):
        import yaml

        return yaml.safe_load(data)


class _yaml_edit(_yaml):
    name = 'edit'
    encoding = 'yml'

    def is_admin(self):
        u = delegate.context.user
        return u and u.is_admin()

    def GET(self, key):
        # only allow admin users to edit yaml
        if not self.is_admin():
            return render.permission_denied(key, 'Permission Denied')

        try:
            d = self.get_data(key)
        except web.HTTPError as e:
            if web.ctx.status.lower() == '404 not found':
                d = {'key': key}
            else:
                raise
        return render.edit_yaml(key, self.dump(d))

    def POST(self, key):
        # only allow admin users to edit yaml
        if not self.is_admin():
            return render.permission_denied(key, 'Permission Denied')

        i = web.input(body='', _comment=None)

        if '_save' in i:
            d = self.load(i.body)
            p = web.ctx.site.new(key, d)
            try:
                p._save(i._comment)
            except (client.ClientException, ValidationException) as e:
                add_flash_message('error', str(e))
                return render.edit_yaml(key, i.body)
            raise web.seeother(key + '.yml')
        elif '_preview' in i:
            add_flash_message('Preview not supported')
            return render.edit_yaml(key, i.body)
        else:
            add_flash_message('unknown action')
            return render.edit_yaml(key, i.body)


def _get_user_root():
    user_root = infogami.config.get('infobase', {}).get('user_root', '/user')
    return web.rstrips(user_root, '/')


def _get_bots():
    bots = web.ctx.site.store.values(type='account', name='bot', value='true')
    user_root = _get_user_root()
    return [user_root + '/' + account['username'] for account in bots]


def _get_members_of_group(group_key):
    """Returns keys of all members of the group identifier by group_key."""
    usergroup = web.ctx.site.get(group_key) or {}
    return [m.key for m in usergroup.get('members', [])]


def can_write():
    """
    Any user with bot flag set can write.
    For backward-compatability, all admin users and people in api usergroup are also allowed to write.
    """
    user_key = delegate.context.user and delegate.context.user.key
    bots = (
        _get_members_of_group('/usergroup/api')
        + _get_members_of_group('/usergroup/admin')
        + _get_bots()
    )
    return user_key in bots


# overwrite the implementation of can_write in the infogami API plugin with this one.
api.can_write = can_write


class Forbidden(web.HTTPError):
    def __init__(self, msg=''):
        web.HTTPError.__init__(self, '403 Forbidden', {}, msg)


class BadRequest(web.HTTPError):
    def __init__(self, msg=''):
        web.HTTPError.__init__(self, '400 Bad Request', {}, msg)


class new:
    """API to create new author/edition/work/publisher/series."""

    def prepare_query(self, query):
        """
        Add key to query and returns the key.
        If query is a list multiple queries are returned.
        """
        if isinstance(query, list):
            return [self.prepare_query(q) for q in query]
        else:
            type = query['type']
            if isinstance(type, dict):
                type = type['key']
            query['key'] = web.ctx.site.new_key(type)
            return query['key']

    def verify_types(self, query):
        if isinstance(query, list):
            for q in query:
                self.verify_types(q)
        else:
            if 'type' not in query:
                raise BadRequest('Missing type')
            type = query['type']
            if isinstance(type, dict):
                if 'key' not in type:
                    raise BadRequest('Bad Type: ' + json.dumps(type))
                type = type['key']

            if type not in [
                '/type/author',
                '/type/edition',
                '/type/work',
                '/type/series',
                '/type/publisher',
            ]:
                raise BadRequest('Bad Type: ' + json.dumps(type))

    def POST(self):
        if not can_write():
            raise Forbidden('Permission Denied.')

        try:
            query = json.loads(web.data())
            h = api.get_custom_headers()
            comment = h.get('comment')
            action = h.get('action')
        except Exception as e:
            raise BadRequest(str(e))

        self.verify_types(query)
        keys = self.prepare_query(query)

        try:
            if not isinstance(query, list):
                query = [query]
            web.ctx.site.save_many(query, comment=comment, action=action)
        except client.ClientException as e:
            raise BadRequest(str(e))

        # graphite/statsd tracking of bot edits
        user = delegate.context.user and delegate.context.user.key
        if user.lower().endswith('bot'):
            botname = user.replace('/people/', '', 1)
            botname = botname.replace('.', '-')
            key = 'ol.edits.bots.' + botname
            openlibrary.core.stats.increment(key)
        return json.dumps(keys)


api and api.add_hook('new', new)


@public
def changequery(query=None, **kw):
    if query is None:
        query = web.input(_method='get', _unicode=False)
    for k, v in kw.items():
        if v is None:
            query.pop(k, None)
        else:
            query[k] = v

    query = {
        k: (list(map(web.safestr, v)) if isinstance(v, list) else web.safestr(v))
        for k, v in query.items()
    }
    out = web.ctx.get('readable_path', web.ctx.path)
    if query:
        out += '?' + urllib.parse.urlencode(query, doseq=True)
    return out


# Hack to limit recent changes offset.
# Large offsets are blowing up the database.

from infogami.core.db import get_recent_changes as _get_recentchanges

import urllib


@public
def get_recent_changes(*a, **kw):
    if 'offset' in kw and kw['offset'] > 5000:
        return []
    else:
        return _get_recentchanges(*a, **kw)


@public
def most_recent_change():
    if 'cache_most_recent' in infogami.config.features:
        v = web.ctx.site._request('/most_recent')
        v.thing = web.ctx.site.get(v.key)
        v.author = v.author and web.ctx.site.get(v.author)
        v.created = client.parse_datetime(v.created)
        return v
    else:
        return get_recent_changes(limit=1)[0]


@public
def get_cover_id(key):
    try:
        _, cat, oln = key.split('/')
        return requests.get(
            f"https://covers.openlibrary.org/{cat}/query?olid={oln}&limit=1"
        ).json()[0]
    except (IndexError, json.decoder.JSONDecodeError, TypeError, ValueError):
        return None


local_ip = None


class invalidate(delegate.page):
    path = '/system/invalidate'

    def POST(self):
        global local_ip
        if local_ip is None:
            local_ip = socket.gethostbyname(socket.gethostname())

        if (
            web.ctx.ip != '127.0.0.1'
            and web.ctx.ip.rsplit('.', 1)[0] != local_ip.rsplit('.', 1)[0]
        ):
            raise Forbidden('Allowed only in the local network.')

        data = json.loads(web.data())
        if not isinstance(data, list):
            data = [data]
        for d in data:
            thing = client.Thing(web.ctx.site, d['key'], client.storify(d))
            client._run_hooks('on_new_version', thing)
        return delegate.RawText('ok')


def save_error():
    t = datetime.datetime.utcnow()
    name = '%04d-%02d-%02d/%02d%02d%02d%06d' % (
        t.year,
        t.month,
        t.day,
        t.hour,
        t.minute,
        t.second,
        t.microsecond,
    )

    path = infogami.config.get('errorlog', 'errors') + '/' + name + '.html'
    dir = os.path.dirname(path)
    if not os.path.exists(dir):
        os.makedirs(dir)

    error = web.safestr(web.djangoerror())
    f = open(path, 'w')
    f.write(error)
    f.close()

    print('error saved to', path, file=web.debug)
    return name


def internalerror():
    i = web.input(_method='GET', debug='false')
    name = save_error()

    # TODO: move this stats stuff to plugins\openlibrary\stats.py
    # Can't have sub-metrics, so can't add more info
    openlibrary.core.stats.increment('ol.internal-errors')
    increment_error_count('ol.internal-errors-segmented')

    # TODO: move this to plugins\openlibrary\sentry.py
    from openlibrary.plugins.openlibrary.sentry import sentry

    if sentry.enabled:
        sentry.capture_exception_webpy()

    if i.debug.lower() == 'true':
        raise web.debugerror()
    else:
        msg = render.site(render.internalerror(name))
        raise web.internalerror(web.safestr(msg))


delegate.app.internalerror = internalerror
delegate.add_exception_hook(save_error)


class memory(delegate.page):
    path = '/debug/memory'

    def GET(self):
        import guppy

        h = guppy.hpy()
        return delegate.RawText(str(h.heap()))


def _get_relatedcarousels_component(workid):
    if 'env' not in web.ctx:
        delegate.fakeload()
    work = web.ctx.site.get('/works/%s' % workid) or {}
    component = render_template('books/RelatedWorksCarousel', work)
    return {0: str(component)}


def get_cached_relatedcarousels_component(*args, **kwargs):
    memoized_get_component_metadata = cache.memcache_memoize(
        _get_relatedcarousels_component,
        "book.bookspage.component.relatedcarousels",
        timeout=dateutil.HALF_DAY_SECS,
    )
    return (
        memoized_get_component_metadata(*args, **kwargs)
        or memoized_get_component_metadata.update(*args, **kwargs)[0]
    )


class Partials(delegate.page):
    path = '/partials'

    def GET(self):
        i = web.input(workid=None, _component=None)
        component = i.pop("_component")
        partial = {}
        if component == "RelatedWorkCarousel":
            partial = _get_relatedcarousels_component(i.workid)
        return delegate.RawText(json.dumps(partial), content_type="application/json")


def is_bot():
    r"""Generated on ol-www1 within /var/log/nginx with:

    cat access.log | grep -oh "; \w*[bB]ot" | sort --unique | awk '{print tolower($2)}'
    cat access.log | grep -oh "; \w*[sS]pider" | sort --unique | awk '{print tolower($2)}'

    Manually removed singleton `bot` (to avoid overly complex grep regex)
    """
    user_agent_bots = [
        'sputnikbot',
        'dotbot',
        'semrushbot',
        'googlebot',
        'yandexbot',
        'monsidobot',
        'kazbtbot',
        'seznambot',
        'dubbotbot',
        '360spider',
        'redditbot',
        'yandexmobilebot',
        'linkdexbot',
        'musobot',
        'mojeekbot',
        'focuseekbot',
        'behloolbot',
        'startmebot',
        'yandexaccessibilitybot',
        'uptimerobot',
        'femtosearchbot',
        'pinterestbot',
        'toutiaospider',
        'yoozbot',
        'parsijoobot',
        'equellaurlbot',
        'donkeybot',
        'paperlibot',
        'nsrbot',
        'discordbot',
        'ahrefsbot',
        '`googlebot',
        'coccocbot',
        'buzzbot',
        'laserlikebot',
        'baiduspider',
        'bingbot',
        'mj12bot',
        'yoozbotadsbot',
    ]
    if not web.ctx.env.get('HTTP_USER_AGENT'):
        return True
    user_agent = web.ctx.env['HTTP_USER_AGENT'].lower()
    return any([bot in user_agent for bot in user_agent_bots])


def setup_template_globals():
    # must be imported here, otherwise silently messes up infogami's import execution
    # order, resulting in random errors like the the /account/login.json endpoint
    # defined in accounts.py being ignored, and using the infogami endpoint instead.
    from openlibrary.book_providers import (
        get_best_edition,
        get_book_provider,
        get_book_provider_by_name,
        get_cover_url,
    )

    web.template.Template.globals.update(
        {
            'next': next,
            'sorted': sorted,
            'zip': zip,
            'tuple': tuple,
            'hash': hash,
            'urlquote': web.urlquote,
            'isbn_13_to_isbn_10': isbn_13_to_isbn_10,
            'isbn_10_to_isbn_13': isbn_10_to_isbn_13,
            'NEWLINE': '\n',
            'random': random.Random(),
            'get_lang': lambda: web.ctx.lang,
            'ceil': math.ceil,
            'get_best_edition': get_best_edition,
            'get_book_provider': get_book_provider,
            'get_book_provider_by_name': get_book_provider_by_name,
            'get_cover_url': get_cover_url,
            # bad use of globals
            'is_bot': is_bot,
            'time': time,
            'input': web.input,
            'dumps': json.dumps,
        }
    )


def setup_context_defaults():
    from infogami.utils import context

    context.defaults.update({'features': [], 'user': None, 'MAX_VISIBLE_BOOKS': 5})


def setup():
    from openlibrary.plugins.openlibrary import (
        sentry,
        home,
        borrow_home,
        stats,
        support,
        events,
        design,
        status,
        authors,
    )

    sentry.setup()
    home.setup()
    design.setup()
    borrow_home.setup()
    stats.setup()
    support.setup()
    events.setup()
    status.setup()
    authors.setup()

    from openlibrary.plugins.openlibrary import api

    delegate.app.add_processor(web.unloadhook(stats.stats_hook))

    if infogami.config.get('dev_instance') is True:
        from openlibrary.plugins.openlibrary import dev_instance

        dev_instance.setup()

    setup_context_defaults()
    setup_template_globals()


setup()
