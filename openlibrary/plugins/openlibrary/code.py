"""
Open Library Plugin.
"""

import datetime
import gzip
import json
import logging
import math
import os
import random
import socket
import sys
from time import time
from urllib.parse import parse_qs, urlencode

import requests
import web
import yaml

import infogami
from openlibrary.core import db
from openlibrary.core.batch_imports import (
    batch_import,
)
from openlibrary.i18n import gettext as _
from openlibrary.plugins.upstream.utils import get_coverstore_public_url, setup_requests

# make sure infogami.config.features is set
if not hasattr(infogami.config, 'features'):
    infogami.config.features = []  # type: ignore[attr-defined]

import openlibrary.core.stats
from infogami.core.db import ValidationException
from infogami.infobase import client
from infogami.utils import delegate, features
from infogami.utils.app import metapage
from infogami.utils.view import (
    add_flash_message,
    public,
    render,
    render_template,
    safeint,
)
from openlibrary.core.lending import get_availability
from openlibrary.core.models import Edition
from openlibrary.plugins.openlibrary import processors
from openlibrary.plugins.openlibrary.stats import increment_error_count
from openlibrary.utils.isbn import canonical, isbn_10_to_isbn_13, isbn_13_to_isbn_10

delegate.app.add_processor(processors.ReadableUrlProcessor())
delegate.app.add_processor(processors.ProfileProcessor())
delegate.app.add_processor(processors.CORSProcessor(cors_prefixes={'/api/'}))
delegate.app.add_processor(processors.PreferenceProcessor())
# Refer to https://github.com/internetarchive/openlibrary/pull/10005 to force patron's to login
# delegate.app.add_processor(processors.RequireLogoutProcessor())

try:
    from infogami.plugins.api import code as api
except:
    api = None  # type: ignore[assignment]

# http header extension for OL API
infogami.config.http_ext_header_uri = 'http://openlibrary.org/dev/docs/api'  # type: ignore[attr-defined]

# setup special connection with caching support
from openlibrary.plugins.openlibrary import connection

client._connection_types['ol'] = connection.OLConnection  # type: ignore[assignment]
infogami.config.infobase_parameters = {'type': 'ol'}

# set up infobase schema. required when running in standalone mode.
from openlibrary.core import schema

schema.register_schema()

from openlibrary.core import models

models.register_models()
models.register_types()

import openlibrary.core.lists.model as list_models

list_models.register_models()

# Remove movefiles install hook. openlibrary manages its own files.
infogami._install_hooks = [
    h for h in infogami._install_hooks if h.__name__ != 'movefiles'
]

from openlibrary.plugins.openlibrary import bulk_tag, lists

lists.setup()
bulk_tag.setup()

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

    with gzip.open(filename) if filename.endswith('.gz') else open(filename) as file:
        queries = [json.loads(line) for line in file]

    print(web.ctx.site.save_many(queries))


class routes(delegate.page):
    path = '/developers/routes'

    def GET(self):
        class ModulesToStr(json.JSONEncoder):
            def default(self, obj):
                if isinstance(obj, metapage):
                    return obj.__module__ + '.' + obj.__name__
                return super().default(obj)

        from openlibrary import code  # noqa: PLC0415

        return '<pre>%s</pre>' % json.dumps(
            code.delegate.pages,
            sort_keys=True,
            cls=ModulesToStr,
            indent=4,
            separators=(',', ': '),
        )


class team(delegate.page):
    path = '/about/team'

    def GET(self):
        return render_template("about/index.html")


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
        from infogami.core.code import edit  # noqa: PLC0415

        key = web.ctx.site.new_key('/type/edition')
        web.ctx.path = key
        return edit().POST(key)


class widget(delegate.page):
    path = r'(/works/OL\d+W|/books/OL\d+M)/widget'

    def GET(self, key: str):  # type: ignore[override]
        olid = key.split('/')[-1]
        item = web.ctx.site.get(key)
        is_work = key.startswith('/works/')
        item['olid'] = olid
        item['availability'] = get_availability(
            'openlibrary_work' if is_work else 'openlibrary_edition',
            [olid],
        ).get(olid)
        item['authors'] = [
            web.storage(key=a.key, name=a.name or None) for a in item.get_authors()
        ]
        return delegate.RawText(
            render_template('widget', format_work_data(item) if is_work else item),
            content_type='text/html',
        )


def format_work_data(work):
    d = dict(work)

    key = work.get('key', '')
    # New solr stores the key as /works/OLxxxW
    if not key.startswith("/works/"):
        key = "/works/" + key

    d['url'] = key
    d['title'] = work.get('title', '')

    if 'author_key' in work and 'author_name' in work:
        d['authors'] = [
            {"key": key, "name": name}
            for key, name in zip(work['author_key'], work['author_name'])
        ]

    if 'cover_edition_key' in work:
        coverstore_url = get_coverstore_public_url()
        d['cover_url'] = f"{coverstore_url}/b/olid/{work['cover_edition_key']}-M.jpg"

    d['read_url'] = "//archive.org/stream/" + work['ia'][0]
    return d


class addauthor(delegate.page):
    path = '/addauthor'

    def POST(self):
        i = web.input('name')
        if len(i.name) < 2:
            return web.badrequest()
        key = web.ctx.site.new_key('/type/author')
        web.ctx.path = key
        web.ctx.site.save(
            {'key': key, 'name': i.name, 'type': {'key': '/type/author'}},
            comment='New Author',
        )
        raise web.HTTPError('200 OK', {}, key)


class clonebook(delegate.page):
    def GET(self):

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
                {
                    'type': [{'id': t.key, 'name': t.key}],
                    'name': web.safestr(t.name),
                    'guid': t.key,
                    'id': t.key,
                    'article': {'id': t.key},
                }
                for t in things
            ]
        else:
            result = []
        callback = i.pop('callback', None)
        d = {
            'status': '200 OK',
            'query': dict(i, escape='html'),
            'code': '/api/status/ok',
            'result': result,
        }

        if callback:
            data = f'{callback}({json.dumps(d)})'
        else:
            data = json.dumps(d)
        raise web.HTTPError('200 OK', {}, data)


class blurb(delegate.page):
    path = '/suggest/blurb/(.*)'

    def GET(self, path):
        i = web.input()
        author = web.ctx.site.get('/' + path)
        body = ''
        if author.birth_date or author.death_date:
            body = f'{author.birth_date} - {author.death_date}'
        else:
            body = '%s' % author.date

        body += '<br/>'
        if author.bio:
            body += web.safestr(author.bio)

        result = {'body': body, 'media_type': 'text/html', 'text_encoding': 'utf-8'}
        d = {'status': '200 OK', 'code': '/api/status/ok', 'result': result}
        if callback := i.pop('callback', None):
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
    with open(path, 'w') as file:
        file.write(text)


def change_ext(filename, ext):
    filename, _ = os.path.splitext(filename)
    if ext:
        filename = filename + ext
    return filename


def get_pages(type, processor):
    pages = web.ctx.site.things({'type': type})
    for p in pages:
        processor(web.ctx.site.get(p))


class robotstxt(delegate.page):
    path = '/robots.txt'

    def GET(self):
        web.header('Content-Type', 'text/plain')
        is_dev = 'dev' in infogami.config.features or web.ctx.host != 'openlibrary.org'
        robots_file = 'norobots.txt' if is_dev else 'robots.txt'
        return web.ok(open(f'static/{robots_file}').read())


@web.memoize
def fetch_ia_js(filename: str) -> str:
    return requests.get(f'https://archive.org/includes/{filename}').text


class ia_js_cdn(delegate.page):
    path = r'/cdn/archive.org/(donate\.js|athena\.js)'

    def GET(self, filename):
        web.header('Content-Type', 'text/javascript')
        web.header("Cache-Control", "max-age=%d" % (24 * 3600))
        return web.ok(fetch_ia_js(filename))


class serviceworker(delegate.page):
    path = '/sw.js'

    def GET(self):
        web.header('Content-Type', 'text/javascript')
        return web.ok(open('static/build/sw.js').read())


class assetlinks(delegate.page):
    path = '/.well-known/assetlinks'

    def GET(self):
        web.header('Content-Type', 'application/json')
        return web.ok(open('static/.well-known/assetlinks.json').read())


class opensearchxml(delegate.page):
    path = '/opensearch.xml'

    def GET(self):
        web.header('Content-Type', 'text/plain')
        return web.ok(open('static/opensearch.xml').read())


class health(delegate.page):
    path = '/health'

    def GET(self):
        web.header('Content-Type', 'text/plain')
        return web.ok('OK')


def remove_high_priority(query: str) -> str:
    """
    Remove `high_priority=true` and `high_priority=false` from query parameters,
    as the API expects to pass URL parameters through to another query, and
    these may interfere with that query.

    >>> remove_high_priority('high_priority=true&v=1')
    'v=1'
    """
    query_params = parse_qs(query)
    query_params.pop("high_priority", None)
    new_query = urlencode(query_params, doseq=True)
    return new_query


class batch_imports(delegate.page):
    """
    The batch import endpoint. Expects a JSONL file POSTed with multipart/form-data.
    """

    path = '/import/batch/new'

    def GET(self):
        return render_template("batch_import.html", batch_result=None)

    def POST(self):
        user_key = delegate.context.user and delegate.context.user.key

        if not user_key:
            raise Forbidden("Must be logged in to create a batch import.")

        import_status = (
            "pending"
            if user_key in _get_members_of_group("/usergroup/admin")
            else "needs_review"
        )

        # Get the upload from web.py. See the template for the <form> used.
        batch_result = None
        form_data = web.input()
        if form_data.get("batchImportFile"):
            batch_result = batch_import(
                form_data['batchImportFile'], import_status=import_status
            )
        elif form_data.get("batchImportText"):
            batch_result = batch_import(
                form_data['batchImportText'].encode("utf-8"),
                import_status=import_status,
            )
        else:
            add_flash_message(
                'error',
                'Either attach a JSONL file or copy/paste JSONL into the text area.',
            )

        return render_template("batch_import.html", batch_result=batch_result)


class BatchImportView(delegate.page):
    path = r'/import/batch/(\d+)'

    def GET(self, batch_id):
        i = web.input(page=1, limit=10, sort='added_time asc')
        page = int(i.page)
        limit = int(i.limit)
        sort = i.sort

        valid_sort_fields = ['added_time', 'import_time', 'status']
        sort_field, sort_order = sort.split()
        if sort_field not in valid_sort_fields or sort_order not in ['asc', 'desc']:
            sort_field = 'added_time'
            sort_order = 'asc'

        offset = (page - 1) * limit

        batch = db.select('import_batch', where='id=$batch_id', vars=locals())[0]
        total_rows = db.query(
            'SELECT COUNT(*) AS count FROM import_item WHERE batch_id=$batch_id',
            vars=locals(),
        )[0].count

        rows = db.select(
            'import_item',
            where='batch_id=$batch_id',
            order=f'{sort_field} {sort_order}',
            limit=limit,
            offset=offset,
            vars=locals(),
        )

        status_counts = db.query(
            'SELECT status, COUNT(*) AS count FROM import_item WHERE batch_id=$batch_id GROUP BY status',
            vars=locals(),
        )

        return render_template(
            'batch_import_view.html',
            batch=batch,
            rows=rows,
            total_rows=total_rows,
            page=page,
            limit=limit,
            sort=sort,
            status_counts=status_counts,
        )


class BatchImportApprove(delegate.page):
    """
    Approve `batch_id`, with a `status` of `needs_review`, for import.

    Making a GET as an admin to this endpoint will change a batch's status from
    `needs_review` to `pending`.
    """

    path = r'/import/batch/approve/(\d+)'

    def GET(self, batch_id):

        user_key = delegate.context.user and delegate.context.user.key
        if user_key not in _get_members_of_group("/usergroup/admin"):
            raise Forbidden('Permission Denied.')

        db.query(
            """
            UPDATE import_item
            SET status = 'pending'
            WHERE batch_id = $1 AND status = 'needs_review';
            """,
            (batch_id,),
        )

        return web.found(f"/import/batch/{batch_id}")


class BatchImportPendingView(delegate.page):
    """
    Endpoint for viewing `needs_review` batch imports.
    """

    path = r"/import/batch/pending"

    def GET(self):
        i = web.input(page=1, limit=10, sort='added_time asc')
        page = int(i.page)
        limit = int(i.limit)
        sort = i.sort

        valid_sort_fields = ['added_time', 'import_time', 'status']
        sort_field, sort_order = sort.split()
        if sort_field not in valid_sort_fields or sort_order not in ['asc', 'desc']:
            sort_field = 'added_time'
            sort_order = 'asc'

        offset = (page - 1) * limit

        rows = db.query(
            """
            SELECT batch_id, MIN(status) AS status, MIN(comments) AS comments, MIN(added_time) AS added_time, MAX(submitter) AS submitter
            FROM import_item
            WHERE status = 'needs_review'
            GROUP BY batch_id;
            """,
            vars=locals(),
        )

        return render_template(
            "batch_import_pending_view",
            rows=rows,
            page=page,
            limit=limit,
        )


class isbn_lookup(delegate.page):
    """The endpoint for /isbn"""

    path = r'/(?:isbn|ISBN)/(.{10,})'

    def GET(self, isbn: str):
        input = web.input(high_priority=False)
        isbn = isbn if isbn.upper().startswith("B") else canonical(isbn)
        high_priority = input.get("high_priority") == "true"
        if "high_priority" in web.ctx.env.get('QUERY_STRING'):
            web.ctx.env['QUERY_STRING'] = remove_high_priority(
                web.ctx.env.get('QUERY_STRING')
            )

        # Preserve the url type (e.g. `.json`) and query params
        ext = ''
        if web.ctx.encoding and web.ctx.path.endswith('.' + web.ctx.encoding):
            ext = '.' + web.ctx.encoding
        if web.ctx.env.get('QUERY_STRING'):
            ext += '?' + web.ctx.env['QUERY_STRING']

        try:
            if ed := Edition.from_isbn(isbn_or_asin=isbn, high_priority=high_priority):
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
            from openlibrary import accounts  # noqa: PLC0415
            from openlibrary.plugins.importapi.code import (  # noqa: PLC0415
                BookImportError,
                ia_importapi,
            )

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
            from infogami.utils import template  # noqa: PLC0415

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
            from openlibrary.plugins.openlibrary import opds  # noqa: PLC0415

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
            from infogami.utils import template  # noqa: PLC0415

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
        data = {'key': key, 'revision': v}
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

        return yaml.safe_dump(d, indent=4, allow_unicode=True, default_flow_style=False)

    def load(self, data):

        return yaml.safe_load(data)


class _yaml_edit(_yaml):
    name = 'edit'
    encoding = 'yml'

    def is_admin(self):
        u = delegate.context.user
        return u and (u.is_admin() or u.is_super_librarian())

    def GET(self, key):
        # only allow admin users to edit yaml
        if not self.is_admin():
            return render.permission_denied(key, 'Permission Denied')

        try:
            d = self.get_data(key)
        except web.HTTPError:
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
def changequery(query=None, _path=None, **kw):
    if query is None:
        query = web.input(_method='get', _unicode=False)
    for k, v in kw.items():
        if v is None:
            query.pop(k, None)
        else:
            query[k] = v

    query = {
        k: [web.safestr(s) for s in v] if isinstance(v, list) else web.safestr(v)
        for k, v in query.items()
    }
    out = _path or web.ctx.get('readable_path', web.ctx.path)
    if query:
        out += '?' + urllib.parse.urlencode(query, doseq=True)
    return out


# Hack to limit recent changes offset.
# Large offsets are blowing up the database.

import urllib

from infogami.core.db import get_recent_changes as _get_recentchanges


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
    with open(path, 'w') as file:
        file.write(error)

    print('error saved to', path, file=web.debug)
    return name


def internalerror():
    name_webpy_error = save_error()

    exception_type, exception_value, _ = sys.exc_info()

    # TODO: move this stats stuff to plugins\openlibrary\stats.py
    # Can't have sub-metrics, so can't add more info
    openlibrary.core.stats.increment('ol.internal-errors')
    increment_error_count('ol.internal-errors-segmented')

    # TODO: move this to plugins\openlibrary\sentry.py
    from openlibrary.plugins.openlibrary.sentry import sentry  # noqa: PLC0415

    sentry_event_id: str | None = None
    if sentry.enabled:
        sentry_event_id = sentry.capture_exception_webpy()

    if features.is_enabled('debug'):
        raise web.debugerror()
    else:
        msg = render.site(
            render.internalerror(
                name_webpy_error,
                sentry_event_id,
                etype=exception_type,
                evalue=exception_value,
            )
        )
        raise web.internalerror(web.safestr(msg))


delegate.app.internalerror = internalerror
delegate.add_exception_hook(save_error)


class memory(delegate.page):
    path = '/debug/memory'

    def GET(self):
        import guppy  # noqa: PLC0415

        h = guppy.hpy()
        return delegate.RawText(str(h.heap()))


def is_bot():
    r"""Generated on ol-www1 within /var/log/nginx with:

    cat access.log | grep -oh "; \w*[bB]ot" | sort --unique | awk '{print tolower($2)}'
    cat access.log | grep -oh "; \w*[sS]pider" | sort --unique | awk '{print tolower($2)}'

    Manually removed singleton `bot` (to avoid overly complex grep regex)
    """
    if 'is_bot' in web.ctx:
        return web.ctx.is_bot

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
        'ahrefsbot',
        'amazonbot',
        'applebot',
        'bingbot',
        'brightbot',
        'gptbot',
        'petalbot',
        'semanticscholarbot',
        'yandex.com/bots',
        'icc-crawler',
    ]
    if not web.ctx.env.get('HTTP_USER_AGENT'):
        return True
    user_agent = web.ctx.env['HTTP_USER_AGENT'].lower()
    return any(bot in user_agent for bot in user_agent_bots)


def setup_template_globals():
    # must be imported here, otherwise silently messes up infogami's import execution
    # order, resulting in random errors like the the /account/login.json endpoint
    # defined in accounts.py being ignored, and using the infogami endpoint instead.
    from openlibrary.book_providers import (  # noqa: PLC0415
        get_best_edition,
        get_book_provider,
        get_book_provider_by_name,
        get_cover_url,
    )

    def get_supported_languages():
        return {
            "cs": {"code": "cs", "localized": _('Czech'), "native": "Čeština"},
            "de": {"code": "de", "localized": _('German'), "native": "Deutsch"},
            "en": {"code": "en", "localized": _('English'), "native": "English"},
            "es": {"code": "es", "localized": _('Spanish'), "native": "Español"},
            "fr": {"code": "fr", "localized": _('French'), "native": "Français"},
            "hi": {"code": "hi", "localized": _('Hindi'), "native": "हिंदी"},
            "hr": {"code": "hr", "localized": _('Croatian'), "native": "Hrvatski"},
            "it": {"code": "it", "localized": _('Italian'), "native": "Italiano"},
            "pt": {"code": "pt", "localized": _('Portuguese'), "native": "Português"},
            "ro": {"code": "ro", "localized": _('Romanian'), "native": "Română"},
            "sc": {"code": "sc", "localized": _('Sardinian'), "native": "Sardu"},
            "te": {"code": "te", "localized": _('Telugu'), "native": "తెలుగు"},
            "uk": {"code": "uk", "localized": _('Ukrainian'), "native": "Українська"},
            "zh": {"code": "zh", "localized": _('Chinese'), "native": "中文"},
        }

    web.template.Template.globals.update(
        {
            'cookies': web.cookies,
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
            'choose_random_from': random.choice,
            'get_lang': lambda: web.ctx.lang,
            'get_supported_languages': get_supported_languages,
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
    from infogami.utils import context  # noqa: PLC0415

    context.defaults.update({'features': [], 'user': None, 'MAX_VISIBLE_BOOKS': 5})


def setup():
    from openlibrary.plugins.importapi import import_ui  # noqa: PLC0415
    from openlibrary.plugins.openlibrary import (  # noqa: PLC0415
        authors,
        borrow_home,
        design,
        events,
        home,
        partials,
        sentry,
        stats,
        status,
        swagger,
    )

    sentry.setup()
    home.setup()
    design.setup()
    borrow_home.setup()
    stats.setup()
    events.setup()
    status.setup()
    authors.setup()
    swagger.setup()
    partials.setup()
    import_ui.setup()

    from openlibrary.plugins.openlibrary import (  # noqa: PLC0415
        api,  # noqa: F401 side effects may be needed
        librarian_dashboard,  # noqa: F401 import required
    )

    delegate.app.add_processor(web.unloadhook(stats.stats_hook))

    if infogami.config.get('dev_instance') is True:
        from openlibrary.plugins.openlibrary import dev_instance  # noqa: PLC0415

        dev_instance.setup()

    setup_context_defaults()
    setup_template_globals()
    setup_requests()


setup()
