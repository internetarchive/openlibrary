"""Lists implementation.
"""

import json
import random
from dataclasses import dataclass, field
from typing import Literal, cast
from urllib.parse import parse_qs

import web

import openlibrary.core.helpers as h
from infogami.infobase import client, common
from infogami.utils import delegate
from infogami.utils.view import public, render_template, require_login
from openlibrary.accounts import get_current_user
from openlibrary.core import cache, formats
from openlibrary.core.lists.model import (
    AnnotatedSeedDict,
    List,
    SeedSubjectString,
    ThingReferenceDict,
)
from openlibrary.core.models import ThingKey
from openlibrary.coverstore.code import render_list_preview_image
from openlibrary.i18n import gettext as _
from openlibrary.plugins.upstream import spamcheck, utils
from openlibrary.plugins.upstream.account import MyBooksTemplate
from openlibrary.plugins.upstream.addbook import safe_seeother
from openlibrary.plugins.worksearch import subjects
from openlibrary.utils import olid_to_key


def subject_key_to_seed(key: subjects.SubjectPseudoKey) -> SeedSubjectString:
    name_part = key.split("/")[-1].replace(",", "_").replace("__", "_")
    if name_part.split(":")[0] in ("place", "person", "time"):
        return name_part
    else:
        return "subject:" + name_part


def is_seed_subject_string(seed: str) -> bool:
    subject_type = seed.split(":")[0]
    return subject_type in ("subject", "place", "person", "time")


def is_empty_annotated_seed(seed: AnnotatedSeedDict) -> bool:
    """
    An empty seed can be represented as a simple SeedDict
    """
    return not seed.get('notes')


Seed = ThingReferenceDict | SeedSubjectString | AnnotatedSeedDict
"""
The JSON-friendly seed representation (as opposed to `openlibrary.core.lists.model.Seed`).
Can either a thing reference, a subject key, or an annotated seed.
"""


@dataclass
class ListRecord:
    key: str | None = None
    name: str = ''
    description: str = ''
    seeds: list[Seed] = field(default_factory=list)

    @staticmethod
    def normalize_input_seed(
        seed: ThingReferenceDict | AnnotatedSeedDict | str,
    ) -> Seed:
        if isinstance(seed, str):
            if seed.startswith('/subjects/'):
                return subject_key_to_seed(seed)
            elif seed.startswith('/'):
                return {'key': seed}
            elif is_seed_subject_string(seed):
                return seed
            else:
                return {'key': olid_to_key(seed)}
        elif 'thing' in seed:
            annotated_seed = cast(AnnotatedSeedDict, seed)  # Appease mypy

            if is_empty_annotated_seed(annotated_seed):
                return ListRecord.normalize_input_seed(annotated_seed['thing'])
            elif annotated_seed['thing']['key'].startswith('/subjects/'):
                return subject_key_to_seed(annotated_seed['thing']['key'])
            else:
                return annotated_seed
        elif seed['key'].startswith('/subjects/'):
            thing_ref = cast(ThingReferenceDict, seed)  # Appease mypy
            return subject_key_to_seed(thing_ref['key'])
        else:
            return seed

    @staticmethod
    def from_input():
        DEFAULTS = {
            'key': None,
            'name': '',
            'description': '',
            'seeds': [],
        }
        if data := web.data():
            # If the requests has data, parse it and use it to populate the list
            if web.ctx.env.get('CONTENT_TYPE') == 'application/json':
                i = {} | DEFAULTS | json.loads(data)
            else:
                form_data = {
                    # By default all the values are lists
                    k: v[0]
                    for k, v in parse_qs(bytes.decode(data)).items()
                }
                i = {} | DEFAULTS | utils.unflatten(form_data)
        else:
            # Otherwise read from the query string
            i = utils.unflatten(web.input(**DEFAULTS))

        normalized_seeds = [
            ListRecord.normalize_input_seed(seed)
            for seed_list in i['seeds']
            for seed in (
                seed_list.split(',') if isinstance(seed_list, str) else [seed_list]
            )
        ]
        normalized_seeds = [
            seed
            for seed in normalized_seeds
            if seed and (isinstance(seed, str) or seed.get('key') or seed.get('thing'))
        ]
        return ListRecord(
            key=i['key'],
            name=i['name'],
            description=i['description'],
            seeds=normalized_seeds,
        )

    def to_thing_json(self):
        return {
            "key": self.key,
            "type": {"key": "/type/list"},
            "name": self.name,
            "description": self.description,
            "seeds": self.seeds,
        }


class lists_home(delegate.page):
    path = "/lists"

    def GET(self):
        delegate.context.setdefault('cssfile', 'lists')
        return render_template("lists/home")


SeedType = Literal['subject', 'author', 'work', 'edition']


def seed_key_to_seed_type(key: str) -> SeedType:
    match key.split('/')[1]:
        case 'subjects':
            return 'subject'
        case 'authors':
            return 'author'
        case 'works':
            return 'work'
        case 'books':
            return 'edition'
        case _:
            raise ValueError(f'Invalid seed key: {key}')


@public
def get_seed_info(doc):
    """Takes a thing, determines what type it is, and returns a seed summary"""
    seed_type = seed_key_to_seed_type(doc.key)
    match seed_type:
        case 'subject':
            seed = subject_key_to_seed(doc.key)
            title = doc.name
        case 'work' | 'edition':
            seed = {"key": doc.key}
            title = doc.get("title", "untitled")
        case 'author':
            seed = {"key": doc.key}
            title = doc.get('name', 'name missing')
        case _:
            raise ValueError(f'Invalid seed type: {seed_type}')
    return {
        "seed": seed,
        "type": seed_type,
        "title": web.websafe(title),
        "remove_dialog_html": _(
            'Are you sure you want to remove <strong>%(title)s</strong> from your list?',
            title=web.websafe(title),
        ),
    }


@public
def get_list_data(list, seed, include_cover_url=True):
    list_items = []
    for s in list.get_seeds():
        list_items.append(s.key)

    d = web.storage(
        {
            "name": list.name or "",
            "key": list.key,
            "active": list.has_seed(seed) if seed else False,
            "list_items": list_items,
        }
    )
    if include_cover_url:
        cover = list.get_cover() or list.get_default_cover()
        d['cover_url'] = (
            cover and cover.url("S")
        ) or "/images/icons/avatar_book-sm.png"
        if 'None' in d['cover_url']:
            d['cover_url'] = "/images/icons/avatar_book-sm.png"

    d['owner'] = None
    if owner := list.get_owner():
        d['owner'] = web.storage(displayname=owner.displayname or "", key=owner.key)
    return d


@public
def get_user_lists(seed_info):
    user = get_current_user()
    if not user:
        return []
    user_lists = user.get_lists(sort=True)
    seed = seed_info['seed'] if seed_info else None
    return [get_list_data(user_list, seed) for user_list in user_lists]


class lists_partials(delegate.page):
    path = "/lists/partials"
    encoding = "json"

    def GET(self):
        partials = self.get_partials()
        return delegate.RawText(json.dumps(partials))

    def get_partials(self):
        user_lists = get_user_lists(None)

        dropper = render_template('lists/dropper_lists', user_lists)
        list_data = {
            list_data['key']: {
                'members': list_data['list_items'],
                'listName': list_data['name'],
            }
            for list_data in user_lists
        }

        return {
            'dropper': str(dropper),
            'listData': list_data,
        }


class lists(delegate.page):
    """Controller for displaying lists of a seed or lists of a person."""

    path = "(/(?:people|books|works|authors|subjects)/[^/]+)/lists"

    def is_enabled(self):
        return "lists" in web.ctx.features

    def GET(self, path):
        # If logged in patron is viewing their lists page, use MyBooksTemplate
        if path.startswith("/people/"):
            username = path.split('/')[-1]

            mb = MyBooksTemplate(username, 'lists')
            if not mb.user:
                raise web.notfound()

            template = render_template(
                "lists/lists.html", mb.user, mb.user.get_lists(), show_header=False
            )
            return mb.render(
                template=template,
                header_title=_("Lists (%(count)d)", count=len(mb.lists)),
            )
        else:
            doc = self.get_doc(path)
            if not doc:
                raise web.notfound()

            lists = doc.get_lists()
            return render_template("lists/lists.html", doc, lists, show_header=True)

    def get_doc(self, key):
        if key.startswith("/subjects/"):
            s = subjects.get_subject(key)
            if s.work_count > 0:
                return s
            else:
                return None
        else:
            return web.ctx.site.get(key)


class lists_edit(delegate.page):
    path = r"(/people/[^/]+)?(/lists/OL\d+L)/edit"

    def GET(self, user_key: str | None, list_key: str):  # type: ignore[override]
        key = (user_key or '') + list_key
        if not web.ctx.site.can_write(key):
            return render_template(
                "permission_denied",
                web.ctx.fullpath,
                f"Permission denied to edit {key}.",
            )

        lst = cast(List | None, web.ctx.site.get(key))
        if lst is None:
            raise web.notfound()
        return render_template("type/list/edit", lst, new=False)

    def POST(self, user_key: str | None, list_key: str | None = None):  # type: ignore[override]
        key = (user_key or '') + (list_key or '')

        if not web.ctx.site.can_write(key):
            return render_template(
                "permission_denied",
                web.ctx.fullpath,
                f"Permission denied to edit {key}.",
            )

        list_record = ListRecord.from_input()
        if not list_record.name:
            raise web.badrequest('A list name is required.')

        # Creating a new list
        if not list_key:
            list_num = web.ctx.site.seq.next_value("list")
            list_key = f"/lists/OL{list_num}L"
            list_record.key = (user_key or '') + list_key

        web.ctx.site.save(
            list_record.to_thing_json(),
            action="lists",
            comment=web.input(_comment="")._comment or None,
        )

        # If content type json, return json response
        if web.ctx.env.get('CONTENT_TYPE') == 'application/json':
            return delegate.RawText(json.dumps({'key': list_record.key}))
        else:
            return safe_seeother(list_record.key)


class lists_add_account(delegate.page):
    path = r"/account/lists/add"

    @require_login
    def GET(self):
        return web.seeother(f'{get_current_user().key}/lists/add{web.ctx.query}')


class lists_add(delegate.page):
    path = r"(/people/[^/]+)?/lists/add"

    def GET(self, user_key: str | None):  # type: ignore[override]
        if user_key and not web.ctx.site.can_write(user_key):
            return render_template(
                "permission_denied",
                web.ctx.fullpath,
                f"Permission denied to edit {user_key}.",
            )
        list_record = ListRecord.from_input()
        # Only admins can add global lists for now
        admin_only = not user_key
        return render_template(
            "type/list/edit", list_record, new=True, admin_only=admin_only
        )

    def POST(self, user_key: str | None):  # type: ignore[override]
        return lists_edit().POST(user_key, None)


class lists_delete(delegate.page):
    path = r"((?:/people/[^/]+)?/lists/OL\d+L)/delete"
    encoding = "json"

    def POST(self, key):
        doc = web.ctx.site.get(key)
        if doc is None or doc.type.key != '/type/list':
            raise web.notfound()

        # Deletes list preview from memcache, if it exists
        cache_key = "core.patron_lists.%s" % web.safestr(doc.key)
        cache.memcache_cache.delete(cache_key)

        doc = {"key": key, "type": {"key": "/type/delete"}}
        try:
            result = web.ctx.site.save(doc, action="lists", comment="Deleted list.")
        except client.ClientException as e:
            web.ctx.status = e.status
            web.header("Content-Type", "application/json")
            return delegate.RawText(e.json)

        web.header("Content-Type", "application/json")
        return delegate.RawText('{"status": "ok"}')


class lists_json(delegate.page):
    path = "(/(?:people|books|works|authors|subjects)/[^/]+)/lists"
    encoding = "json"
    content_type = "application/json"

    def GET(self, path):
        if path.startswith("/subjects/"):
            doc = subjects.get_subject(path)
        else:
            doc = web.ctx.site.get(path)
        if not doc:
            raise web.notfound()

        i = web.input(offset=0, limit=50)
        i.offset = h.safeint(i.offset, 0)
        i.limit = h.safeint(i.limit, 50)

        i.limit = min(i.limit, 100)
        i.offset = max(i.offset, 0)

        lists = self.get_lists(doc, limit=i.limit, offset=i.offset)
        return delegate.RawText(self.dumps(lists))

    def get_lists(self, doc, limit=50, offset=0):
        lists = doc.get_lists(limit=limit, offset=offset)
        size = len(lists)

        if offset or len(lists) == limit:
            # There could be more lists than len(lists)
            size = len(doc.get_lists(limit=1000))

        d = {
            "links": {"self": web.ctx.path},
            "size": size,
            "entries": [lst.preview() for lst in lists],
        }
        if offset + len(lists) < size:
            d['links']['next'] = web.changequery(limit=limit, offset=offset + limit)

        if offset:
            offset = max(0, offset - limit)
            d['links']['prev'] = web.changequery(limit=limit, offset=offset)

        return d

    def forbidden(self):
        headers = {"Content-Type": self.get_content_type()}
        data = {"message": "Permission denied."}
        return web.HTTPError("403 Forbidden", data=self.dumps(data), headers=headers)

    def POST(self, user_key):
        # POST is allowed only for /people/foo/lists
        if not user_key.startswith("/people/"):
            raise web.nomethod()

        site = web.ctx.site
        user = site.get(user_key)

        if not user:
            raise web.notfound()

        if not site.can_write(user_key):
            raise self.forbidden()

        data = self.loads(web.data())
        # TODO: validate data

        seeds = self.process_seeds(data.get('seeds', []))

        lst = user.new_list(
            name=data.get('name', ''),
            description=data.get('description', ''),
            tags=data.get('tags', []),
            seeds=seeds,
        )

        if spamcheck.is_spam(lst):
            raise self.forbidden()

        try:
            result = site.save(
                lst.dict(),
                comment="Created new list.",
                action="lists",
                data={"list": {"key": lst.key}, "seeds": seeds},
            )
        except client.ClientException as e:
            headers = {"Content-Type": self.get_content_type()}
            data = {"message": str(e)}
            raise web.HTTPError(e.status, data=self.dumps(data), headers=headers)

        web.header("Content-Type", self.get_content_type())
        return delegate.RawText(self.dumps(result))

    @staticmethod
    def process_seeds(
        seeds: ThingReferenceDict | subjects.SubjectPseudoKey | ThingKey,
    ) -> list[Seed]:
        return [ListRecord.normalize_input_seed(seed) for seed in seeds]

    def get_content_type(self):
        return self.content_type

    def dumps(self, data):
        return formats.dump(data, self.encoding)

    def loads(self, text):
        return formats.load(text, self.encoding)


class lists_yaml(lists_json):
    encoding = "yml"
    content_type = "text/yaml"


def get_list(key, raw=False):
    if lst := web.ctx.site.get(key):
        if raw:
            return lst.dict()
        return {
            "links": {
                "self": lst.key,
                "seeds": lst.key + "/seeds",
                "subjects": lst.key + "/subjects",
                "editions": lst.key + "/editions",
            },
            "name": lst.name or None,
            "type": {"key": lst.key},
            "description": ((lst.description and str(lst.description)) or None),
            "seed_count": lst.seed_count,
            "meta": {
                "revision": lst.revision,
                "created": lst.created.isoformat(),
                "last_modified": lst.last_modified.isoformat(),
            },
        }


class list_view_json(delegate.page):
    path = r"((?:/people/[^/]+)?/lists/OL\d+L)"
    encoding = "json"
    content_type = "application/json"

    def GET(self, key):
        i = web.input()
        raw = i.get("_raw") == "true"
        lst = get_list(key, raw=raw)
        if not lst or lst['type']['key'] == '/type/delete':
            raise web.notfound()
        web.header("Content-Type", self.content_type)
        return delegate.RawText(formats.dump(lst, self.encoding))


class list_view_yaml(list_view_json):
    encoding = "yml"
    content_type = "text/yaml"


@public
def get_list_seeds(key):
    if lst := web.ctx.site.get(key):
        seeds = [seed.dict() for seed in lst.get_seeds()]
        return {
            "links": {"self": key + "/seeds", "list": key},
            "size": len(seeds),
            "entries": seeds,
        }


class list_seeds(delegate.page):
    path = r"((?:/people/[^/]+)?/lists/OL\d+L)/seeds"
    encoding = "json"

    content_type = "application/json"

    def GET(self, key):
        lst = get_list_seeds(key)
        if not lst:
            raise web.notfound()

        return delegate.RawText(
            formats.dump(lst, self.encoding), content_type=self.content_type
        )

    def POST(self, key):
        site = web.ctx.site

        lst = cast(List | None, site.get(key))
        if not lst:
            raise web.notfound()

        if not site.can_write(key):
            raise self.forbidden()

        data = formats.load(web.data(), self.encoding)

        data.setdefault("add", [])
        data.setdefault("remove", [])

        # support /subjects/foo and /books/OL1M along with subject:foo and {"key": "/books/OL1M"}.
        for seed in lists_json.process_seeds(data["add"]):
            lst.add_seed(seed)

        for seed in lists_json.process_seeds(data["remove"]):
            lst.remove_seed(seed)

        seeds = []
        for seed in data["add"] + data["remove"]:
            if isinstance(seed, dict):
                seeds.append(seed['key'])
            else:
                seeds.append(seed)

        changeset_data = {
            "list": {"key": key},
            "seeds": seeds,
            "add": data["add"],
            "remove": data["remove"],
        }

        d = lst._save(comment="Updated list.", action="lists", data=changeset_data)
        web.header("Content-Type", self.content_type)
        return delegate.RawText(formats.dump(d, self.encoding))


class list_seed_yaml(list_seeds):
    encoding = "yml"
    content_type = 'text/yaml; charset="utf-8"'


def get_list_editions(key, offset=0, limit=50, api=False):
    if lst := cast(List | None, web.ctx.site.get(key)):
        offset = offset or 0  # enforce sane int defaults
        all_editions = list(lst.get_editions())
        editions = all_editions[offset : offset + limit]
        if api:
            return make_collection(
                size=len(all_editions),
                entries=[e.dict() for e in editions],
                limit=limit,
                offset=offset,
                key=key,
            )
        return editions


class list_editions_json(delegate.page):
    path = r"((?:/people/[^/]+)?/lists/OL\d+L)/editions"
    encoding = "json"

    content_type = "application/json"

    def GET(self, key):
        i = web.input(limit=50, offset=0)
        limit = h.safeint(i.limit, 50)
        offset = h.safeint(i.offset, 0)
        editions = get_list_editions(key, offset=offset, limit=limit, api=True)
        if not editions:
            raise web.notfound()
        return delegate.RawText(
            formats.dump(editions, self.encoding), content_type=self.content_type
        )


class list_editions_yaml(list_editions_json):
    encoding = "yml"
    content_type = 'text/yaml; charset="utf-8"'


def make_collection(size, entries, limit, offset, key=None):
    d = {
        "size": size,
        "start": offset,
        "end": offset + limit,
        "entries": entries,
        "links": {
            "self": web.changequery(),
        },
    }

    if offset + len(entries) < size:
        d['links']['next'] = web.changequery(limit=limit, offset=offset + limit)

    if offset:
        d['links']['prev'] = web.changequery(limit=limit, offset=max(0, offset - limit))

    if key:
        d['links']['list'] = key

    return d


class list_subjects_json(delegate.page):
    path = r"((?:/people/[^/]+)?/lists/OL\d+L)/subjects"
    encoding = "json"
    content_type = "application/json"

    def GET(self, key):
        lst = cast(List | None, web.ctx.site.get(key))
        if not lst:
            raise web.notfound()

        i = web.input(limit=20)
        limit = h.safeint(i.limit, 20)

        data = self.get_subjects(lst, limit=limit)
        data['links'] = {"self": key + "/subjects", "list": key}

        text = formats.dump(data, self.encoding)
        return delegate.RawText(text, content_type=self.content_type)

    def get_subjects(self, lst, limit):
        data = lst.get_subjects(limit=limit)
        for key, subjects_ in data.items():
            data[key] = [self._process_subject(s) for s in subjects_]
        return dict(data)

    def _process_subject(self, s):
        key = s['key']
        if key.startswith("subject:"):
            key = "/subjects/" + web.lstrips(key, "subject:")
        else:
            key = "/subjects/" + key
        return {"name": s['name'], "count": s['count'], "url": key}


class list_subjects_yaml(list_subjects_json):
    encoding = "yml"
    content_type = 'text/yaml; charset="utf-8"'


class lists_embed(delegate.page):
    path = r"((?:/people/[^/]+)?/lists/OL\d+L)/embed"

    def GET(self, key):
        doc = web.ctx.site.get(key)
        if doc is None or doc.type.key != '/type/list':
            raise web.notfound()
        return render_template("type/list/embed", doc)


class export(delegate.page):
    path = r"((?:/people/[^/]+)?/lists/OL\d+L)/export"

    def GET(self, key):
        lst = cast(List | None, web.ctx.site.get(key))
        if not lst:
            raise web.notfound()

        format = web.input(format="html").format

        if format == "html":
            data = self.get_exports(lst)
            html = render_template(
                "lists/export_as_html",
                lst,
                data["editions"],
                data["works"],
                data["authors"],
            )
            return delegate.RawText(html)
        elif format == "bibtex":
            data = self.get_exports(lst)
            html = render_template(
                "lists/export_as_bibtex",
                lst,
                data["editions"],
                data["works"],
                data["authors"],
            )
            return delegate.RawText(html)
        elif format == "json":
            data = self.get_exports(lst, raw=True)
            web.header("Content-Type", "application/json")
            return delegate.RawText(json.dumps(data))
        elif format == "yaml":
            data = self.get_exports(lst, raw=True)
            web.header("Content-Type", "application/yaml")
            return delegate.RawText(formats.dump_yaml(data))
        else:
            raise web.notfound()

    def get_exports(self, lst: List, raw: bool = False) -> dict[str, list]:
        export_data = lst.get_export_list()
        if "editions" in export_data:
            export_data["editions"] = sorted(
                export_data["editions"],
                key=lambda doc: doc['last_modified']['value'],
                reverse=True,
            )
        if "works" in export_data:
            export_data["works"] = sorted(
                export_data["works"],
                key=lambda doc: doc['last_modified']['value'],
                reverse=True,
            )
        if "authors" in export_data:
            export_data["authors"] = sorted(
                export_data["authors"],
                key=lambda doc: doc['last_modified']['value'],
                reverse=True,
            )

        if not raw:
            if "editions" in export_data:
                export_data["editions"] = [
                    self.make_doc(e) for e in export_data["editions"]
                ]
                lst.preload_authors(export_data["editions"])
            else:
                export_data["editions"] = []
            if "works" in export_data:
                export_data["works"] = [self.make_doc(e) for e in export_data["works"]]
                lst.preload_authors(export_data["works"])
            else:
                export_data["works"] = []
            if "authors" in export_data:
                export_data["authors"] = [
                    self.make_doc(e) for e in export_data["authors"]
                ]
                lst.preload_authors(export_data["authors"])
            else:
                export_data["authors"] = []
        return export_data

    def make_doc(self, rawdata):
        data = web.ctx.site._process_dict(common.parse_query(rawdata))
        doc = client.create_thing(web.ctx.site, data['key'], data)
        return doc


class feeds(delegate.page):
    path = r"((?:/people/[^/]+)?/lists/OL\d+L)/feeds/(updates).(atom)"

    def GET(self, key, name, fmt):
        lst = cast(List | None, web.ctx.site.get(key))
        if lst is None:
            raise web.notfound()
        text = getattr(self, 'GET_' + name + '_' + fmt)(lst)
        return delegate.RawText(text)

    def GET_updates_atom(self, lst):
        web.header("Content-Type", 'application/atom+xml; charset="utf-8"')
        return render_template("lists/feed_updates.xml", lst)


def setup():
    pass


def _get_recently_modified_lists(limit, offset=0):
    """Returns the most recently modified lists as list of dictionaries.

    This function is memoized for better performance.
    """
    # this function is memozied with background=True option.
    # web.ctx must be initialized as it won't be available to the background thread.
    if 'env' not in web.ctx:
        delegate.fakeload()

    keys = web.ctx.site.things(
        {
            "type": "/type/list",
            "sort": "-last_modified",
            "limit": limit,
            "offset": offset,
        }
    )
    lists = web.ctx.site.get_many(keys)

    return [lst.dict() for lst in lists]


def get_cached_recently_modified_lists(limit, offset=0):
    f = cache.memcache_memoize(
        _get_recently_modified_lists,
        key_prefix="lists.get_recently_modified_lists",
        timeout=0,
    )  # dateutil.HALF_HOUR_SECS)
    return f(limit, offset=offset)


def _preload_lists(lists):
    """Preloads all referenced documents for each list.
    List can be either a dict of a model object.
    """
    keys = set()

    for xlist in lists:
        if not isinstance(xlist, dict):
            xlist = xlist.dict()

        owner = xlist['key'].rsplit("/lists/", 1)[0]
        if owner:
            keys.add(owner)

        for seed in xlist.get("seeds", []):
            if isinstance(seed, dict) and "key" in seed:
                keys.add(seed['key'])

    web.ctx.site.get_many(list(keys))


def _get_active_lists_in_random(limit=20, preload=True):
    if 'env' not in web.ctx:
        delegate.fakeload()

    lists = []
    offset = 0

    while len(lists) < limit:
        result = get_cached_recently_modified_lists(limit * 5, offset=offset)
        if not result:
            break

        offset += len(result)
        # ignore lists with 4 or less seeds
        lists += [xlist for xlist in result if len(xlist.get("seeds", [])) > 4]

    if len(lists) > limit:
        lists = random.sample(lists, limit)

    if preload:
        _preload_lists(lists)

    return lists


@public
def get_active_lists_in_random(limit=20, preload=True):
    f = cache.memcache_memoize(
        _get_active_lists_in_random,
        key_prefix="lists.get_active_lists_in_random",
        timeout=0,
    )
    lists = f(limit=limit, preload=preload)
    # convert rawdata into models.
    return [web.ctx.site.new(xlist['key'], xlist) for xlist in lists]


class lists_preview(delegate.page):
    path = r"((?:/people/[^/]+)?/lists/OL\d+L)/preview.png"

    def GET(self, lst_key):
        image_bytes = render_list_preview_image(lst_key)
        web.header("Content-Type", "image/png")
        return delegate.RawText(image_bytes)
