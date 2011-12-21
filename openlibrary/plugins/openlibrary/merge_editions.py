'Merge editions'
import web
from openlibrary.utils import uniq, dicthash
from infogami.utils import delegate
from infogami.utils.view import render_template

class merge_editions(delegate.page):
    path = '/editions/merge'

    def is_enabled(self):
        return "merge-editions" in web.ctx.features

    def GET(self):
        i = web.input(key=[],merge_key=[])
        keys = uniq(i.key)
        merge_keys = uniq(i.merge_key)
        assert all(k is not None for k in merge_keys)
        if not merge_keys:
            return render_template('merge/editions', keys)

        full_keys = ['/books/' + k for k in merge_keys]
        editions = [web.ctx.site.get('/books/' + k) for k in merge_keys]

        merged = {}

        for k in 'source_records', 'ia_box_id':
            merged[k] = []
            for e in editions:
                if e.get(k) and isinstance(e[k], basestring):
                    e[k] = [e[k]]
                if e.get(k):
                    assert isinstance(e[k], list)
                for sr in e.get(k, []):
                    if sr not in merged[k]:
                        merged[k].append(sr)

        all_keys = set()
        for e in editions:
            all_keys.update(e.keys())

        for k in all_keys:
            if k in ('source_records', 'ia_box_id'):
                continue
#            if all(e[k] == editions[0][k] for e in editions[1:]):
#                merged = editions[0][k]

        return render_template('merge/editions2', editions, all_keys, merged)

def setup():
    pass
