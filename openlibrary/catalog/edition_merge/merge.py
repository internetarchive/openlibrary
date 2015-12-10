#!/usr/bin/python

import MySQLdb, datetime, re, sys
sys.path.append('/1/src/openlibrary')
from openlibrary.api import OpenLibrary, Reference
from flask import Flask, render_template, request, flash, redirect, url_for, g
from collections import defaultdict
app = Flask(__name__)

re_edition_key = re.compile('^/books/OL(\d+)M$')

ol = OpenLibrary('http://openlibrary.org/')
ol.login('EdwardBot', 'As1Wae9b')

@app.before_request
def before_request():
    g.db = MySQLdb.connect(db='merge_editions')

@app.after_request
def after_request(r):
    g.db.close()
    return r

re_nonword = re.compile(r'\W', re.U)

rows = 200

app.secret_key = 'rt9%s#)5kid$!u*5_@*$f2f_%jq++nl3@d%=7f%v4&78^m4p7c'

@app.route("/")
def index():
    page = int(request.args.get('page', 1))
    cur = g.db.cursor()
    cur.execute('select count(*) from merge where done is null')
    total = cur.fetchone()[0]
    cur.execute('select count(*) from merge where done is null and unmerge_count = 0')
    easy = cur.fetchone()[0]
    cur.execute('select ia, editions, unmerge_count from merge where done is null limit %s offset %s', [rows, (page-1) * rows])
    reply = cur.fetchall()
    return render_template('index.html', merge_list=reply, total=total, rows=rows, page=page, easy=easy )

def run_merge(ia):
    cur = g.db.cursor()
    cur.execute('select editions from merge where ia=%s', ia)
    [ekeys] = cur.fetchone()
    ekeys = ['/books/OL%dM' % x for x in sorted(int(re_edition_key.match(ekey).group(1)) for ekey in ekeys.split(' '))]
    min_ekey = ekeys[0]

    editions = [ol.get(ekey) for ekey in ekeys]
    editions_by_key = dict((e['key'][7:], e) for e in editions)
    merged = build_merged(editions)

    missing = []
    for k, v in merged.items():
        if v is not None:
            continue
        use_ekey = request.form.get(k)
        if use_ekey is None:
            missing.append(k)
            continue
        merged[k] = editions_by_key[use_ekey][k]
    if missing:
        flash('please select: ' + ', '.join(missing))
        return redirect(url_for('merge', ia=ia))

    master = ol.get(min_ekey)
    for k, v in merged.items():
        master[k] = v

    updates = []
    updates.append(master)
    for ekey in ekeys:
        if ekey == min_ekey:
            continue
        ol_redirect = {
            'type': Reference('/type/redirect'),
            'location': min_ekey,
            'key': ekey,
        }
        updates.append(ol_redirect)
    #print len(updates), min_ekey
    try:
        ol.save_many(updates, 'merge lending editions')
    except:
        #for i in updates:
        #    print i
        raise
    cur.execute('update merge set done=now() where ia=%s', [ia])

    flash(ia + ' merged')
    return redirect(url_for('index'))

def build_merged(editions):
    all_keys = set()

    for e in editions:
        for k in 'classifications', 'identifiers':
            if k in e and not e[k]:
                del e[k]

    for e in editions:
        all_keys.update(e.keys())

    for k in 'latest_revision', 'revision', 'created', 'last_modified', 'key', 'type', 'genres':
        if k in all_keys:
            all_keys.remove(k)

    for k in all_keys.copy():
        if k.startswith('subject'):
            all_keys.remove(k)

    merged = {}
    k = 'publish_date'
    publish_dates = set(e[k] for e in editions if k in e and len(e[k]) != 4)

    k = 'pagination'
    all_pagination = set(e[k] for e in editions if e.get(k))

    one_item_lists = {}
    for k in 'lc_classifications', 'publishers', 'contributions', 'series':
        one_item_lists[k] = set(e[k][0].strip('.') for e in editions if e.get(k) and len(set(e[k])) == 1)

    for k in 'source_records', 'ia_box_id':
        merged[k] = []
        for e in editions:
            for sr in e.get(k, []):
                if sr not in merged[k]:
                    merged[k].append(sr)

    for k in ['other_titles', 'isbn_10', 'series']:
        if k not in all_keys:
            continue
        merged[k] = []
        for e in editions:
            for sr in e.get(k, []):
                if sr not in merged[k]:
                    merged[k].append(sr)


    k = 'ocaid'
    for e in editions:
        if e.get(k) and 'ia:' + e[k] not in merged['source_records']:
            merged['source_records'].append(e[k])

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

    for k in all_keys:
        if k in ('source_records', 'ia_box_id', 'identifiers'):
            continue

        uniq = defaultdict(list)
        for num, e in enumerate(editions):
            if e.get(k):
                if k == 'publish_date' and len(e[k]) == 4 and e[k].isdigit and any(e[k] in pd for pd in publish_dates):
                    continue
                if k == 'pagination' and any(len(i) > len(e[k]) and e[k] in i for i in all_pagination):
                    continue
                if k in one_item_lists and len(set(e.get(k, []))) == 1 and any(len(i) > len(e[k][0].strip('.')) and e[k][0].strip('.') in i for i in one_item_lists[k]):
                    continue
                if k == 'publish_country' and any_publish_country and e.get(k, '').strip().startswith('xx'):
                    continue
                if k == 'edition_name' and e[k].endswith(' ed edition'):
                    e[k] = e[k][:-len(' edition')]
                uniq[re_nonword.sub('', `e[k]`.lower())].append(num)

        if len(uniq) == 1:
            #merged[k] = uniq.keys()[0]
            merged[k] = editions[uniq.values()[0][0]][k]
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
        merged[k] = None

    return merged

@app.route("/merge/<ia>", methods=['GET', 'POST'])
def merge(ia):
    if request.method == 'POST':
        return run_merge(ia)

    cur = g.db.cursor()
    cur.execute('select ia, editions, done from merge where ia = %s', [ia])
    ia, ekeys, done = cur.fetchone()
    ekeys = ['/books/OL%dM' % x for x in sorted(int(re_edition_key.match(ekey).group(1)) for ekey in ekeys.split(' '))]
    min_ekey = ekeys[0]

    editions = [ol.get(ekey) for ekey in ekeys]

    merged = build_merged(editions)
    all_keys = merged.keys()

    wkeys = set()
    works = []
    if False: 
        for e in editions:
            for wkey in e.get('works', []):
                if wkey not in wkeys:
                    w = ol.get(wkey)
                    works.append(w)
                    q = {'type':'/type/edition', 'works':wkey, 'limit': 1000}
                    work_editions = ol.query(q)
                    w['number_of_editions'] = len(work_editions)
                    wkeys.add(wkey)

    return render_template('merge.html',
            ia=ia,
            editions=editions,
            keys=sorted(all_keys),
            merged = merged,
            ekeys=ekeys,
            works=works,
            master=min_ekey)

if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True)
