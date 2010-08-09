"""Merge authors.
"""
import web

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
                'location': master,
                'limit': 10000,
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
