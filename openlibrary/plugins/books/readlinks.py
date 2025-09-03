"""'Read' api implementation.  This is modeled after the HathiTrust
Bibliographic API, but also includes information about loans and other
editions of the same work that might be available.
"""

import re
import sys

import requests
import web

from infogami import config
from infogami.utils import stats
from infogami.utils.delegate import register_exception
from openlibrary.api import OpenLibrary  # noqa: F401 side effects may be needed
from openlibrary.core import helpers, ia
from openlibrary.plugins.books import dynlinks


def key_to_olid(key):
    return key.split('/')[-1]


def ol_query(name, value):
    query = {
        'type': '/type/edition',
        name: value,
    }
    if keys := web.ctx.site.things(query):
        return keys[0]


def get_solr_select_url():
    c = config.get("plugin_worksearch")
    base_url = c and c.get('solr_base_url')
    return base_url and (base_url + "/select")


def get_work_iaids(wkey):
    # wid = wkey.split('/')[2]
    solr_select_url = get_solr_select_url()
    filter = 'ia'
    q = 'key:' + wkey
    stats.begin('solr', url=wkey)
    solr_select = (
        solr_select_url
        + f"?version=2.2&q.op=AND&q={q}&rows=10&fl={filter}&qt=standard&wt=json&fq=type:work"
    )
    reply = requests.get(solr_select).json()
    stats.end()
    print(reply)
    if reply['response']['numFound'] == 0:
        return []
    return reply["response"]['docs'][0].get(filter, [])


def get_solr_fields_for_works(
    field: str,
    wkeys: list[str],
    clip_limit: int | None = None,
) -> dict[str, list[str]]:
    from openlibrary.plugins.worksearch.search import get_solr  # noqa: PLC0415

    docs = get_solr().get_many(wkeys, fields=['key', field])
    return {doc['key']: doc.get(field, [])[:clip_limit] for doc in docs}


def get_eids_for_wids(wids):
    """To support testing by passing in a list of work-ids - map each to
    it's first edition ID"""
    solr_select_url = get_solr_select_url()
    filter = 'edition_key'
    q = '+OR+'.join(wids)
    solr_select = (
        solr_select_url
        + f"?version=2.2&q.op=AND&q={q}&rows=10&fl=key,{filter}&qt=standard&wt=json&fq=type:work"
    )
    reply = requests.get(solr_select).json()
    if reply['response']['numFound'] == 0:
        return []
    rows = reply['response']['docs']
    result = {r['key']: r[filter][0] for r in rows if len(r.get(filter, []))}
    return result


# Not yet used.  Solr editions aren't up-to-date (6/2011)
def get_solr_edition_records(iaids):
    solr_select_url = get_solr_select_url()
    filter = 'title'
    q = '+OR+'.join('ia:' + id for id in iaids)
    solr_select = (
        solr_select_url
        + f"?version=2.2&q.op=AND&q={q}&rows=10&fl=key,{filter}&qt=standard&wt=json"
    )
    reply = requests.get(solr_select).json()
    if reply['response']['numFound'] == 0:
        return []
    rows = reply['response']['docs']
    return rows
    result = {r['key']: r[filter][0] for r in rows if len(r.get(filter, []))}
    return result


class ReadProcessor:
    def __init__(self, options):
        self.options = options

    def get_item_status(self, ekey, iaid, collections) -> str:
        if 'inlibrary' in collections:
            status = 'lendable'
        else:
            status = 'restricted' if 'printdisabled' in collections else 'full access'

        if status == 'lendable':
            loanstatus = web.ctx.site.store.get(f'ebooks/{iaid}', {'borrowed': 'false'})
            if loanstatus['borrowed'] == 'true':
                status = 'checked out'

        return status

    def get_readitem(self, iaid, orig_iaid, orig_ekey, wkey, status, publish_date):
        meta = self.iaid_to_meta.get(iaid)
        if meta is None:
            return None

        if status == 'missing':
            return None

        if (
            status.startswith('restricted') or status == 'checked out'
        ) and not self.options.get('show_all_items'):
            return None

        edition = self.iaid_to_ed.get(iaid)
        ekey = edition.get('key', '')

        if status == 'full access':
            itemURL = 'http://www.archive.org/stream/%s' % (iaid)
        else:
            # this could be rewrit in terms of iaid...
            itemURL = 'http://openlibrary.org{}/{}/borrow'.format(
                ekey, helpers.urlsafe(edition.get('title', 'untitled'))
            )
        result = {
            # XXX add lastUpdate
            'enumcron': False,
            'match': 'exact' if iaid == orig_iaid else 'similar',
            'status': status,
            'fromRecord': orig_ekey,
            'ol-edition-id': key_to_olid(ekey),
            'ol-work-id': key_to_olid(wkey),
            'publishDate': publish_date,
            'contributor': '',
            'itemURL': itemURL,
        }

        if edition.get('covers'):
            cover_id = edition['covers'][0]
            # can be rewrit in terms of iaid
            # XXX covers url from yaml?
            result['cover'] = {
                "small": "https://covers.openlibrary.org/b/id/%s-S.jpg" % cover_id,
                "medium": "https://covers.openlibrary.org/b/id/%s-M.jpg" % cover_id,
                "large": "https://covers.openlibrary.org/b/id/%s-L.jpg" % cover_id,
            }

        return result

    date_pat = r'\D*(\d\d\d\d)\D*'
    date_re = re.compile(date_pat)

    def make_record(self, bib_keys):
        # XXX implement hathi no-match logic?
        found = False
        for k in bib_keys:
            if k in self.docs:
                found = True
                break
        if not found:
            return None
        doc = self.docs[k]
        data = self.datas[k]
        details = self.detailss.get(k)

        # determine potential ia items for this identifier,
        orig_iaid = doc.get('ocaid')
        doc_works = doc.get('works')
        if doc_works and len(doc_works) > 0:
            wkey = doc_works[0]['key']
        else:
            wkey = None
        if wkey:
            iaids = self.wkey_to_iaids[wkey]
            # rearrange so any scan for this edition is first
            if orig_iaid and orig_iaid in iaids:
                iaids.pop(iaids.index(orig_iaid))
                iaids.insert(0, orig_iaid)
        elif orig_iaid:
            # attempt to handle work-less editions
            iaids = [orig_iaid]
        else:
            iaids = []
        orig_ekey = data['key']

        # Sort iaids.  Is there a more concise way?

        def getstatus(self, iaid):
            meta = self.iaid_to_meta.get(iaid)
            if not meta:
                status = 'missing'
                edition = None
            else:
                collections = meta.get("collection", [])
                edition = self.iaid_to_ed.get(iaid)
            if not edition:
                status = 'missing'
            else:
                ekey = edition.get('key', '')
                status = self.get_item_status(ekey, iaid, collections)
            return status

        def getdate(self, iaid):
            if edition := self.iaid_to_ed.get(iaid):
                m = self.date_re.match(edition.get('publish_date', ''))
                if m:
                    return m.group(1)
            return ''

        iaids_tosort = [
            (iaid, getstatus(self, iaid), getdate(self, iaid)) for iaid in iaids
        ]

        def sortfn(sortitem):
            iaid, status, date = sortitem
            if iaid == orig_iaid and status in {'full access', 'lendable'}:
                isexact = '000'
            else:
                isexact = '999'
            # sort dateless to end
            if date == '':
                date = 5000
            date = int(date)
            # reverse-sort modern works by date
            if status in {'lendable', 'checked out'}:
                date = 10000 - date
            statusvals = {
                'full access': 1,
                'lendable': 2,
                'checked out': 3,
                'restricted': 4,
                'missing': 5,
            }
            return (isexact, statusvals[status], date)

        iaids_tosort.sort(key=sortfn)

        items = [
            self.get_readitem(iaid, orig_iaid, orig_ekey, wkey, status, date)
            for iaid, status, date in iaids_tosort
        ]  # if status != 'missing'
        items = [item for item in items if item]

        ids = data.get('identifiers', {})
        if self.options.get('no_data'):
            returned_data = None
        else:
            returned_data = data
        result = {
            'records': {
                data['key']: {
                    'isbns': [
                        subitem
                        for sublist in (ids.get('isbn_10', []), ids.get('isbn_13', []))
                        for subitem in sublist
                    ],
                    'issns': [],
                    'lccns': ids.get('lccn', []),
                    'oclcs': ids.get('oclc', []),
                    'olids': [key_to_olid(data['key'])],
                    'publishDates': [data.get('publish_date', '')],
                    'recordURL': data['url'],
                    'data': returned_data,
                    'details': details,
                }
            },
            'items': items,
        }

        if self.options.get('debug_items'):
            result['tosort'] = iaids_tosort
        return result

    def process(self, req):
        requests = req.split('|')
        bib_keys = [item for r in requests for item in r.split(';')]

        # filter out 'id:foo' before passing to dynlinks
        bib_keys = [k for k in bib_keys if k[:3].lower() != 'id:']

        self.docs = dynlinks.query_docs(bib_keys)
        if not self.options.get('no_details'):
            self.detailss = dynlinks.process_result_for_details(self.docs)
        else:
            self.detailss = {}
        dp = dynlinks.DataProcessor()
        self.datas = dp.process(self.docs)
        self.works = dp.works

        # XXX control costs below with iaid_limit - note that this may result
        # in no 'exact' item match, even if one exists
        # Note that it's available thru above works/docs
        self.wkey_to_iaids = get_solr_fields_for_works('ia', self.works, 500)
        iaids = [value for sublist in self.wkey_to_iaids.values() for value in sublist]
        self.iaid_to_meta = {iaid: ia.get_metadata(iaid) for iaid in iaids}

        def lookup_iaids(iaids):
            step = 10
            if len(iaids) > step and not self.options.get('debug_things'):
                result = []
                while iaids:
                    result += lookup_iaids(iaids[:step])
                    iaids = iaids[step:]
                return result
            query = {
                'type': '/type/edition',
                'ocaid': iaids,
            }
            result = web.ctx.site.things(query)
            return result

        ekeys = lookup_iaids(iaids)

        # If returned order were reliable, I could skip the below.
        eds = dynlinks.ol_get_many_as_dict(ekeys)
        self.iaid_to_ed = {ed['ocaid']: ed for ed in eds.values()}

        result = {}
        for r in requests:
            bib_keys = r.split(';')
            if r.lower().startswith('id:'):
                result_key = bib_keys.pop(0)[3:]
            else:
                result_key = r
            sub_result = self.make_record(bib_keys)
            if sub_result:
                result[result_key] = sub_result

        if self.options.get('debug_items'):
            result['ekeys'] = ekeys
            result['eds'] = eds
            result['iaids'] = iaids

        return result


def readlinks(req, options):
    try:
        dbstr = 'debug|'
        if req.startswith(dbstr):
            options = {
                'stats': True,
                'show_exception': True,
                'no_data': True,
                'no_details': True,
                'show_all_items': True,
            }
            req = req[len(dbstr) :]
        rp = ReadProcessor(options)

        if options.get('listofworks'):
            """For load-testing, handle a special syntax"""
            wids = req.split('|')
            mapping = get_solr_fields_for_works('edition_key', wids[:5])
            req = '|'.join(('olid:' + k) for k in mapping.values())

        result = rp.process(req)

        if options.get('stats'):
            summary = stats.stats_summary()
            s = {}
            result['stats'] = s
            s['summary'] = summary
            s['stats'] = web.ctx.get('stats', [])
    except:
        print('Error in processing Read API', file=sys.stderr)
        if options.get('show_exception'):
            register_exception()
            result = {'success': False}
        else:
            register_exception()
        result = {}
    return result
