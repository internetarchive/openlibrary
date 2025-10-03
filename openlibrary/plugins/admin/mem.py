import gc

import web

from infogami.utils import delegate  # noqa: F401 side effects may be needed
from infogami.utils.view import render, safeint
from openlibrary.plugins.admin import memory


def render_template(name, *a, **kw):
    return render[name](*a, **kw)


class Object:
    def __init__(self, obj, name=None):
        self.obj = obj
        self.name = name

    def get_id(self):
        return id(self.obj)

    def get_type(self):
        return memory._get_type(self.obj)

    def repr(self):
        try:
            if isinstance(self.obj, (dict, web.threadeddict)):
                from infogami.infobase.utils import prepr  # noqa: PLC0415

                return prepr(self.obj)
            else:
                return repr(self.obj)
        except:
            return "failed"

        return render_template("admin/memory/object", self.obj)

    def get_referrers(self):
        d = []

        for o in gc.get_referrers(self.obj):
            name = None
            if isinstance(o, dict):
                name = web.dictfind(o, self.obj)
                for r in gc.get_referrers(o):
                    if getattr(r, "__dict__", None) is o:
                        o = r
                        break
            elif isinstance(o, dict):  # other dict types
                name = web.dictfind(o, self.obj)

            if not isinstance(name, str):
                name = None

            d.append(Object(o, name))
        return d

    def get_referents(self):
        d = []

        _dict = getattr(self.obj, "__dict__", None)
        if _dict:
            for k, v in self.obj.__dict__.items():
                d.append(Object(v, name=k))

        for o in gc.get_referents(self.obj):
            if o is not _dict:
                d.append(Object(o))
        return d


class _memory:
    path = "/memory"

    def GET(self):
        i = web.input(page=1, sort="diff", prefix="")

        page = safeint(i.page, 1)
        end = page * 50
        begin = end - 50

        if i.sort not in ["count", "mark", "diff"]:
            i.sort = "diff"

        counts = [c for c in memory.get_counts() if c.type.startswith(i.prefix)]
        counts.sort(key=lambda c: c[i.sort], reverse=True)
        return render_template(
            "admin/memory/index", counts[begin:end], page, sort=i.sort
        )

    def POST(self):
        memory.mark()
        raise web.seeother(web.ctx.fullpath)


class _memory_type:
    path = "/memory/type/(.*)"

    def GET(self, type):
        objects = memory.get_objects_by_type(type)

        i = web.input(page=1, diff="false")

        page = safeint(i.page, 1)

        objects = [Object(obj) for obj in memory.get_objects_by_type(type)]

        if i.diff == "true":
            marked = memory._mark_ids.get(type, [])
            objects = [obj for obj in objects if obj.get_id() not in marked]

        return render_template("admin/memory/type", type, objects, page)


def first(it):
    try:
        return next(it)
    except StopIteration:
        return None


class _memory_id:
    path = "/memory/id/(.*)"

    def get_object(self, _id):
        for obj in memory.get_objects():
            if str(id(obj)) == _id:
                return Object(obj)

    def GET(self, _id):
        obj = self.get_object(_id)
        if not obj:
            raise web.notfound()
        return render_template("admin/memory/object", obj)
