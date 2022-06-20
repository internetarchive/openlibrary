"""Lists implementation.
"""
import json
import random
import tempfile
import web

from infogami.utils import delegate
from infogami.utils.view import render_template, public
from infogami.infobase import client, common

from openlibrary.accounts import get_current_user
from openlibrary.core import formats, cache
from openlibrary.core.lists.model import ListMixin
import openlibrary.core.helpers as h
from openlibrary.utils import dateutil
from openlibrary.plugins.upstream import spamcheck
from openlibrary.plugins.upstream.account import MyBooksTemplate
from openlibrary.plugins.worksearch import subjects
from openlibrary.coverstore.code import render_list_preview_image



class lists_home(delegate.page):
    path = "/lists"

    def GET(self):
        delegate.context.setdefault('cssfile', 'lists')
        return render_template("lists/home")


class lists(delegate.page):
    """Controller for displaying lists of a seed or lists of a person."""

    path = "(/(?:people|books|works|authors|subjects)/[^/]+)/lists"

    def is_enabled(self):
        return "lists" in web.ctx.features

    def GET(self, path):
        # If logged in patron is viewing their lists page, use MyBooksTemplate
        if path.startswith("/people/"):
            user = get_current_user()
            username = path.split('/')[-1]

            if user and user.key.split('/')[-1] == username:
                return MyBooksTemplate(username, 'lists').render()
        doc = self.get_doc(path)
        if not doc:
            raise web.notfound()

        lists = doc.get_lists()
        return self.render(doc, lists)

    def get_doc(self, key):
        if key.startswith("/subjects/"):
            s = subjects.get_subject(key)
            if s.work_count > 0:
                return s
            else:
                return None
        else:
            return web.ctx.site.get(key)

    def render(self, doc, lists):
        return render_template("lists/lists.html", doc, lists)


class lists_delete(delegate.page):
    path = r"(/people/[^/]+/lists/OL\d+L)/delete"
    encoding = "json"

    def POST(self, key):
        doc = web.ctx.site.get(key)
        if doc is None or doc.type.key != '/type/list':
            raise web.notfound()

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
            data = {"message": e.message}
            raise web.HTTPError(e.status, data=self.dumps(data), headers=headers)

        web.header("Content-Type", self.get_content_type())
        return delegate.RawText(self.dumps(result))

    def process_seeds(self, seeds):
        def f(seed):
            if isinstance(seed, dict):
                return seed
            elif seed.startswith("/subjects/"):
                seed = seed.split("/")[-1]
                if seed.split(":")[0] not in ["place", "person", "time"]:
                    seed = "subject:" + seed
                seed = seed.replace(",", "_").replace("__", "_")
            elif seed.startswith("/"):
                seed = {"key": seed}
            return seed

        return [f(seed) for seed in seeds]

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
    lst = web.ctx.site.get(key)
    if lst:
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
            "description": (lst.description and str(lst.description) or None),
            "seed_count": lst.seed_count,
            "meta": {
                "revision": lst.revision,
                "created": lst.created.isoformat(),
                "last_modified": lst.last_modified.isoformat(),
            },
        }


class list_view_json(delegate.page):
    path = r"(/people/[^/]+/lists/OL\d+L)"
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
    lst = web.ctx.site.get(key)
    if lst:
        seeds = [seed.dict() for seed in lst.get_seeds()]
        return {
            "links": {"self": key + "/seeds", "list": key},
            "size": len(seeds),
            "entries": seeds,
        }


class list_seeds(delegate.page):
    path = r"(/people/[^/]+/lists/OL\d+L)/seeds"
    encoding = "json"

    content_type = "application/json"

    def GET(self, key):
        lst = get_list_seeds(key)
        if not lst:
            raise web.notfound()
        return delegate.RawText(formats.dump(lst, self.encoding))

    def POST(self, key):
        site = web.ctx.site

        lst = site.get(key)
        if not lst:
            raise web.notfound()

        if not site.can_write(key):
            raise self.forbidden()

        data = formats.load(web.data(), self.encoding)

        data.setdefault("add", [])
        data.setdefault("remove", [])

        # support /subjects/foo and /books/OL1M along with subject:foo and {"key": "/books/OL1M"}.
        process_seeds = lists_json().process_seeds

        for seed in process_seeds(data["add"]):
            lst.add_seed(seed)

        for seed in process_seeds(data["remove"]):
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
            "add": data.get("add", []),
            "remove": data.get("remove", []),
        }

        d = lst._save(comment="Updated list.", action="lists", data=changeset_data)
        web.header("Content-Type", self.content_type)
        return delegate.RawText(formats.dump(d, self.encoding))


class list_seed_yaml(list_seeds):
    encoding = "yml"
    content_type = 'text/yaml; charset="utf-8"'


@public
def get_list_editions(key, offset=0, limit=50, api=False):
    lst = web.ctx.site.get(key)
    if lst:
        offset = offset or 0  # enforce sane int defaults
        all_editions = lst.get_editions(limit=limit, offset=offset, _raw=True)
        editions = all_editions['editions'][offset : offset + limit]
        if api:
            entries = [e.dict() for e in editions if e.pop("seeds") or e]
            return make_collection(
                size=all_editions['count'],
                entries=entries,
                limit=limit,
                offset=offset,
                key=key,
            )
        return editions


class list_editions_json(delegate.page):
    path = r"(/people/[^/]+/lists/OL\d+L)/editions"
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
    path = r"(/people/[^/]+/lists/OL\d+L)/subjects"
    encoding = "json"
    content_type = "application/json"

    def GET(self, key):
        lst = web.ctx.site.get(key)
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
        for key, subjects in data.items():
            data[key] = [self._process_subject(s) for s in subjects]
        return dict(data)

    def _process_subject(self, s):
        key = s['key']
        if key.startswith("subject:"):
            key = "/subjects/" + web.lstrips(key, "subject:")
        else:
            key = "/subjects/" + key
        return {"name": s['name'], "count": s['count'], "url": key}


# This class is defined twice in this file. Should this be list_subjects_yaml() ?
class list_editions_yaml(list_subjects_json):    # type: ignore[no-redef]
    encoding = "yml"
    content_type = 'text/yaml; charset="utf-8"'


class lists_embed(delegate.page):
    path = r"(/people/[^/]+/lists/OL\d+L)/embed"

    def GET(self, key):
        doc = web.ctx.site.get(key)
        if doc is None or doc.type.key != '/type/list':
            raise web.notfound()
        return render_template("type/list/embed", doc)


class export(delegate.page):
    path = r"(/people/[^/]+/lists/OL\d+L)/export"

    def GET(self, key):
        lst = web.ctx.site.get(key)
        if not lst:
            raise web.notfound()

        format = web.input(format="html").format

        if format == "html":
            data = self.get_exports(lst)
            html = render_template("lists/export_as_html", lst, data["editions"], data["works"], data["authors"])
            return delegate.RawText(html)
        elif format == "bibtex":
            data = self.get_exports(lst)
            html = render_template(
                "lists/export_as_bibtex", lst, data["editions"], data["works"], data["authors"]
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

    def get_exports(self, lst: ListMixin, raw: bool = False) -> dict[str, list]:
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
                export_data["editions"] = [self.make_doc(e) for e in export_data["editions"]]
                lst.preload_authors(export_data["editions"])
            else:
                export_data["editions"] = []
            if "works" in export_data:
                export_data["works"] = [self.make_doc(e) for e in export_data["works"]]
                lst.preload_authors(export_data["works"])
            else:
                export_data["works"] = []
            if "authors" in export_data:
                export_data["authors"] = [self.make_doc(e) for e in export_data["authors"]]
                lst.preload_authors(export_data["authors"])
            else:
                export_data["authors"] = []
        return export_data

    def get_editions(self, lst, raw=False):
        editions = sorted(
            lst.get_all_editions(),
            key=lambda doc: doc['last_modified']['value'],
            reverse=True,
        )

        if not raw:
            editions = [self.make_doc(e) for e in editions]
            lst.preload_authors(editions)
        return editions

    def make_doc(self, rawdata):
        data = web.ctx.site._process_dict(common.parse_query(rawdata))
        doc = client.create_thing(web.ctx.site, data['key'], data)
        return doc


class feeds(delegate.page):
    path = r"(/people/[^/]+/lists/OL\d+L)/feeds/(updates).(atom)"

    def GET(self, key, name, fmt):
        lst = web.ctx.site.get(key)
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
        keys.add(owner)

        for seed in xlist.get("seeds", []):
            if isinstance(seed, dict) and "key" in seed:
                keys.add(seed['key'])

    web.ctx.site.get_many(list(keys))


def get_randomized_list_seeds(lst_key):
    """Fetches all the seeds of a list and shuffles them"""
    lst = web.ctx.site.get(lst_key)
    seeds = lst.seeds if lst else []
    random.shuffle(seeds)
    return seeds


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
    path = r"(/people/[^/]+/lists/OL\d+L)/preview.png"

    def GET(self, lst_key):
        image_bytes = render_list_preview_image(lst_key)
        web.header("Content-Type", "image/png")
        return delegate.RawText(image_bytes)
