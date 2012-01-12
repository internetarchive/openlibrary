'Merge editions'
import web, re
from openlibrary.utils import uniq, dicthash
from infogami.utils import delegate
from infogami.utils.view import render_template
from collections import defaultdict

re_nonword = re.compile(r'\W', re.U)

class merge_editions(delegate.page):
    path = '/books/merge'

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
        master = None
        for e in editions:
            if e.key == '/books/' + i.master:
                master = e
                break

        all_keys = set()
        for e in editions:
            for k in e.keys():
                if e[k] is not None and e[k] != {}:
                    all_keys.add(k)

        merged = {}
        possible_values = defaultdict(lambda: defaultdict(int))

        k = 'publish_date'
        publish_dates = set(e[k] for e in editions if k in e and len(e[k]) != 4)

        k = 'pagination'
        all_pagination = set(e[k] for e in editions if e.get(k))

        one_item_lists = {}
        for k in 'lc_classifications', 'publishers', 'contributions', 'series':
            one_item_lists[k] = set(e[k][0].strip('.') for e in editions if e.get(k) and len(set(e[k])) == 1)

        for k in ['other_titles', 'isbn_10', 'series']:
            if k not in all_keys:
                continue
            merged[k] = []
            for e in editions:
                for v in e.get(k, []):
                    if v not in merged[k]:
                        possible_values[k][v] += 1
                        merged[k].append(v)

        k = 'ocaid'
        for e in editions:
            v = e.get(k)
            if not v:
                continue
            possible_values[k][v] += 1
            if 'ia:' + v not in merged.get('source_records', []):
                merged.setdefault('source_records', []).append(v)

        k = 'identifiers'
        if k in all_keys:
            merged[k] = {}
            for e in editions:
                if k not in e:
                    continue
                for a, b in e[k].items():
                    for c in b:
                        if c in merged[k].setdefault(a, []):
                            continue
                        merged[k][a].append(c)

        any_publish_country = False
        k = 'publish_country'
        if k in all_keys:
            for e in editions:
                if e.get(k) and not e[k].strip().startswith('xx'):
                    any_publish_country = True

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

        for k in all_keys:
            if k in ('source_records', 'ia_box_id', 'identifiers', 'ocaid', 'other_titles', 'series'):
                continue
            uniq_values = defaultdict(list)
            for num, e in enumerate(editions):
                v = e.get(k) 
                if v:
                    if isinstance(v, list):
                        for lv in v:
                            possible_values[k][lv] += 1
                    elif not isinstance(v, dict):
                        possible_values[k][v] += 1
                    if k == 'publish_date' and len(v) == 4 and v.isdigit and any(v in pd for pd in publish_dates):
                        continue
                    if k == 'pagination' and any(len(i) > len(v) and v in i for i in all_pagination):
                        continue
                    if k in one_item_lists and len(set(e.get(k, []))) == 1 and any(len(i) > len(v[0].strip('.')) and v[0].strip('.') in i for i in one_item_lists[k]):
                        continue
                    if k == 'publish_country' and any_publish_country and e.get(k, '').strip().startswith('xx'):
                        continue
                    if k == 'edition_name' and v.endswith(' ed edition'):
                        v = v[:-len(' edition')]
                    uniq_values[re_nonword.sub('', `v`.lower())].append(num)

            if len(uniq_values) == 1:
                merged[k] = editions[uniq_values.values()[0][0]][k]
                continue

            if k == 'covers':
                assert all(isinstance(e[k], list) for e in editions if k in e)
                covers = set()
                for e in editions:
                    if k in e:
                        covers.update(c for c in e[k] if c != -1)
                merged['covers'] = sorted(covers)
                continue

            if k == 'notes':
                merged['notes'] = ''
                for e in editions:
                    if e.get('notes'):
                        merged['notes'] += e['notes'] + '\n'
                continue

            if k == 'ocaid':
                for e in editions:
                    if e.get('ocaid'):
                        #assert not e['ocaid'].endswith('goog')
                        merged['ocaid'] = e['ocaid']
                        break
                assert merged['ocaid']
                continue

        return render_template('merge/editions2', master, editions, all_keys, merged, possible_values)

def setup():
    pass
