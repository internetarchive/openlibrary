"""Merge authors.
"""
import web
import simplejson
from infogami.utils import delegate

class MergeAuthorsImpl:
    def merge(self, master, duplicates):
        """Takes the key of master author and a list of duplicate keys
        and merges the duplicates with the master.
        """
        master_author = web.ctx.site.get(master).dict()
        master_author['type']['key'] == '/type/author'
        edition_keys = set()
        work_keys = set()
        updates = []
        master_needs_save = False
        for old in duplicates:
            q = {
                'type': '/type/edition',
                'authors': {'key': old},
                'works': None,
                'limit': 10000,
            }
            editions = web.ctx.site.things(q)
            edition_keys.update(editions)
            for ekey in editions:
                e = web.ctx.site.get(ekey)
                work_keys.update(w['key'] for w in e.get('works', []))
            q = {
                'type': '/type/work',
                'authors': {'author': {'key': old}},
                'limit': 10000,
            }
            work_keys.update(web.ctx.site.things(q))
            old_author = web.ctx.site.get(old)
            if old_author.get('name', ''):
                if old_author.name not in master_author.setdefault('alternate_names', []):
                    master_needs_save = True
                    master_author['alternate_names'].append(old_author.name)
            r = {
                'key': old,
                'type': {'key': '/type/redirect'},
                'location': master
            }
            updates.append(r)

        for wkey in work_keys:
            q = {
                'type': '/type/edition',
                'works': {'key': wkey},
                'limit': 10000,
            }
            edition_keys.update(web.ctx.site.things(q))

            w = web.ctx.site.get(wkey)
            authors = []
            for cur in w['authors']:
                assert cur['type'] == '/type/author_role' or cur['type']['key'] == '/type/author_role'
                assert len(cur.keys()) == 2
                cur = cur['author']['key']
                a = master if cur in duplicates else cur
                if a not in authors:
                    authors.append(a)

            w['authors'] = [{'type': '/type/author_role', 'author': {'key': a}} for a in authors]
            updates.append(w.dict())

        for ekey in edition_keys:
            e = web.ctx.site.get(ekey)
            authors = []
            for cur in e['authors']:
                cur = cur['key']
                a = master if cur in duplicates else cur
                if a not in authors:
                    authors.append(a)

            e['authors'] = [{'key': a} for a in authors]
            updates.append(e.dict())

        if master_needs_save:
            updates.append(master_author)
        data = {
            "master": master,
            "duplicates": list(duplicates)
        }
        return web.ctx.site.save_many(updates, comment='merge authors', action="merge-authors", data=data)

def uniq(values):
    s = set()
    result = []
    for v in values:
        if v not in s:
            s.add(v)
            result.append(v)
    return result

class merge_authors(delegate.page):
    path = '/authors/merge'

    def is_enabled(self):
        return "merge-authors" in web.ctx.features

    def GET(self):
        i = web.input(key=[])
        keys = uniq(i.key)        
        return render_template('merge/authors', keys, top_books_from_author=top_books_from_author)

    def POST(self):
        i = web.input(key=[], master=None, merge_key=[])
        keys = uniq(i.key)
        selected = uniq(i.merge_key)

        # doesn't make sense to merge master with it self.
        if i.master in selected:
            selected.remove(i.master)

        formdata = web.storage(
            master=i.master, 
            selected=selected
        )

        if not i.master or len(selected) == 0:
            return render_template("merge/authors", keys, top_books_from_author=top_books_from_author, formdata=formdata)
        else:                
            # redirect to the master. The master will display a progressbar and call the merge_authors_json to trigger the merge.
            master = web.ctx.site.get("/authors/" + i.master)
            raise web.seeother(master.url() + "?merge=true&duplicates=" + ",".join(selected))

class merge_authors_json(delegate.page):
    """JSON API for merge authors. 

    This is called from the master author page to trigger the merge while displaying progress.
    """
    path = "/authors/merge"
    encoding = "json"

    def is_enabled(self):
        return "merge-authors" in web.ctx.features

    def POST(self):
        jsontext = web.data()
        data = simplejson.loads(json)
        master = data['master']
        duplicates = data['duplicates']
        result = merge_authors().do_merge(master, duplicates)
        return delegate.RawText(json.dumps(result),  content_type="application/json")

def setup():
    pass