""" 'Read' api implementation.  This is modeled after the HathiTrust
Bibliographic API, but also includes information about loans and other
editions of the same work that might be available.
"""
import sys
import urllib

import web
from openlibrary.core import inlibrary
from openlibrary.core import ia
from openlibrary.core import helpers
from openlibrary.api import OpenLibrary
from infogami.infobase import _json as simplejson
from infogami.utils.delegate import register_exception

import dynlinks


def key_to_olid(olkey):
    return olkey.split('/')[-1]


ol = OpenLibrary("http://openlibrary.org")
def get_work_editions(work):
    editions = ol.query({ 'type': '/type/edition',
                          'works': work.key,
                          'limit': False })
    return editions

    # return editions only if this ol knows about them.
    # return [edition for edition in editions if web.ctx.site.get(edition)]


def get_readable_edition_item(edition, work, user_inlibrary, initial_edition):
    ocaid = edition.get('ocaid', False)
    if not ocaid:
        return None
    subjects = work.get_subjects()
    if not subjects:
        return None

    metaxml = ia.get_meta_xml(ocaid)

    collections = metaxml.get("collection", [])

    status = ''
    if 'lendinglibrary' in collections:
        if not 'Lending library' in subjects:
            return None
        status = 'lendable'
    elif 'inlibrary' in collections:
        if not 'In library' in subjects:
            return None
        if not user_inlibrary:
            return None
        status = 'lendable'
    elif 'printdisabled' in collections:
        status = 'restricted'
        return None
    else:
        status = 'full access'

    if status == 'full access':
        itemURL = "http://www.archive.org/stream/%s" % (ocaid)
    else:
        itemURL = u"http://openlibrary.org%s/%s/borrow" % (edition['key'],
                                                           helpers.urlsafe(edition.get("title",
                                                                                       "untitled")))

    if status == 'lendable':
        loanstatus =  web.ctx.site.store.get('ebooks' + edition['key'], {'borrowed': 'false'})
        if loanstatus['borrowed'] == 'true':
            status = 'checked out'

    if edition['key'] == initial_edition['key']:
        match = 'exact'
    else:
        match = 'similar'

    result = {
        'enumcron': False,
        # 'orig': 'University of California'
        # 'htid': ''
        # 'lastUpdate: "" # XXX from edition.last_modified (datetime)
        'match': match,
        'status': status,
        'fromRecord': initial_edition['key'],
        'ol-edition-id': key_to_olid(edition['key']),
        'ol-work-id': key_to_olid(work['key']),
        'contributor': 'contributor',
        'itemURL': itemURL,
        }

    if edition.get('covers'):
        cover_id = edition['covers'][0]
        # XXX covers url from yaml?
        result['cover'] = {
            "small": "http://covers.openlibrary.org/b/id/%s-S.jpg" % cover_id,
            "medium": "http://covers.openlibrary.org/b/id/%s-M.jpg" % cover_id,
            "large": "http://covers.openlibrary.org/b/id/%s-L.jpg" % cover_id,
            }

    return result


def format_one_request(record, data, details):
    edition = web.ctx.site.get(record['key'])

    if not 'works' in record:
        return {}

    work = web.ctx.site.get(record['works'][0]['key']) # xxx

    user_inlibrary = inlibrary.get_library()

    # XXX fix
    thised_item = get_readable_edition_item(edition, work,
                                            user_inlibrary, edition)
    eds = get_work_editions(work)
    eds = [ed for ed in eds if ed != edition['key']]

    eds = web.ctx.site.get_many(eds)

    othered_items = [get_readable_edition_item(ed, work,
                                               user_inlibrary, edition)
                     for ed in eds]
    othered_items = [item for item in othered_items if item]
    if thised_item:
        othered_items.insert(0, thised_item)
    items = othered_items

    isbns = edition.get('isbn_10', [])
    isbns.extend(edition.get('isbn_13', [])) # xxx ? how to handle.

    result = {'records':
                  { edition['key']:
                        { 'isbns': isbns,
                          'issns': [],
                          'lccns': edition.get('lccn', []),
                          'oclcs': edition.get('oclc_numbers', []),
                          'publishDates': [edition['publish_date']],
                          'recordURL': 'http://openlibrary.org%s' % edition['key'],
                          # 'marc-xml': ''
                          'data': data,
                          'details': details,
                          } },
              'items': items }
    return result


def readlink_single(bibkey, options):
    bka = [bibkey]
    r = dynlinks.query_docs(bka)
    (data, details) = [dynlinks.process_result(r, cmd)[bibkey]
                       for cmd in ('data', 'details')]
    if len(r) == 0:
        return []
    record = r[bibkey]
    return format_one_request(record, data, details)
    # (data, details, viewapi) = [dynlinks.process_result(r, cmd)[bibkey]
    #                             for cmd in ('data', 'details', 'viewapi')]
    # return record, edition, work, eds, data, items


def readlink_multiple(bibkey_str, options):
    requests = bibkey_str.split('|')
    # make mapping between maybe-id and key-to-use
    rmap = {}
    for r in requests:
        if r[:3].lower() == 'id:':
            parts = r.split(';')
            if len(parts) != 2:
                return {}
            key = parts[0][3:]
            val = parts[1]
        else:
            key = r
            val = r
        rmap[key] = val
    records = dynlinks.query_docs(rmap.values())
    datas = dynlinks.process_result(records, 'data')
    details = dynlinks.process_result(records, 'details')

    formatted = {}
    for k in records.keys():
        formatted[k] = format_one_request(records[k], datas[k], details[k])

    result = {}
    for k in rmap.keys():
        f = formatted.get(rmap[k], None)
        if f is not None:
            result[k] = f
    
    return result

########################

def ol_query(name, value):
    query = {
        'type': '/type/edition',
        name: value,
    }
    keys = web.ctx.site.things(query)
    if keys:
        return keys[0]


def get_work_iaids(workid):
    wkey = workid.split('/')[2]
    # XXX below for solr_host??
    #     base_url = "http://%s/solr/works" % config.plugin_worksearch.get('solr')
    solr_host = 'ol-solr.us.archive.org:8983'
    solr_select_url = "http://" + solr_host + "/solr/works/select"
    filter = 'ia'
    q = 'key:' + wkey
    solr_select = solr_select_url + "?version=2.2&q.op=AND&q=%s&rows=10&fl=%s&qt=standard&wt=json" % (q, filter)
    json_data = urllib.urlopen(solr_select).read()
    print json_data
    reply = simplejson.loads(json_data)
    if reply['response']['numFound'] == 0:
        return []
    return reply["response"]['docs'][0].get(filter, [])


class ReadProcessor:
    def __init__(self):
        self.set_inlibrary = False

    def get_inlibrary(self):
        if not self.set_inlibrary:
            self.set_inlibrary = True
            self.inlibrary = inlibrary.get_library()
        return self.inlibrary
        
    def get_readitem(self, iaid, orig_iaid, orig_ed_key, work_key, subjects):
        meta = self.iaid_to_meta[iaid]
        collections = meta.get("collection", [])
        status = ''
        if 'lendinglibrary' in collections:
            if not 'Lending library' in subjects:
                status = 'restricted'
            else:
                status = 'lendable'
        elif 'inlibrary' in collections:
            if not 'In library' in subjects:
                status = 'restricted'
            elif not self.get_inlibrary():
                status = 'restricted'
            else:
                status = 'lendable'
        elif 'printdisabled' in collections:
            status = 'restricted'
        else:
            status = 'full access'
        if status == 'restricted':
            return None

        ed_key = self.iaid_to_ed_key.get(iaid)
        if not ed_key:
            # This shouldn't much occur in production, but can easily happen
            # in a dev instance if the record hasn't been imported.
            return None
        edition = self.iaid_to_ed[iaid]

        if status == 'full access':
            itemURL = 'http://www.archive.org/stream/%s' % (iaid)
        else:
            itemURL = u'http://openlibrary.org%s/%s/borrow' % (ed_key,
                                                               helpers.urlsafe(edition.get('title',
                                                                                           'untitled')))
        if status == 'lendable':
            loanstatus =  web.ctx.site.store.get('ebooks' + ed_key, {'borrowed': 'false'})
            if loanstatus['borrowed'] == 'true':
                status = 'checked out'

        result = {
            'enumcron': False,
            'match': 'exact' if iaid == orig_iaid else 'similar',
            'status': status,
            'fromRecord': orig_ed_key,
            'ol-edition-id': key_to_olid(ed_key),
            'ol-work-id': key_to_olid(work_key),
            'contributor': '',
            'itemURL': itemURL,
            }

        if edition.get('covers'):
            cover_id = edition['covers'][0]
            # XXX covers url from yaml?
            result['cover'] = {
                "small": "http://covers.openlibrary.org/b/id/%s-S.jpg" % cover_id,
                "medium": "http://covers.openlibrary.org/b/id/%s-M.jpg" % cover_id,
                "large": "http://covers.openlibrary.org/b/id/%s-L.jpg" % cover_id,
                }

        return result


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
        details = self.detailss[k]
       
        # determine potential ia items for this identifier,
        orig_iaid = doc.get('ocaid')
        doc_works = doc.get('works')
        if doc_works and len(doc_works) > 0:
            work_key = doc_works[0]['key']
        else:
            work_key = None
        work = None
        subjects = []
        if work_key:
            work = self.works.get(work_key)
            subjects = work.get('subjects', [])
            iaids = self.work_to_iaids[work_key]
            # rearrange so any scan for this edition is first
            if orig_iaid and orig_iaid in iaids:
                iaids.pop(iaids.index(orig_iaid))
                iaids.insert(0, orig_iaid)
        elif orig_iaid:
            # attempt to handle work-less editions
            iaids = [ orig_iaid ]
        else:
            iaids = []
        orig_ed_key = data['key']

        items = [self.get_readitem(iaid, orig_iaid, orig_ed_key, work_key, subjects)
                 for iaid in iaids]
        items = [item for item in items if item]

        ids = data.get('identifiers', {})
        result = {'records':
            { data['key']:
                  { 'isbns': sum((ids.get('isbn_10', []), ids.get('isbn_13', [])), []),
                    'issns': [],
                    'lccns': ids.get('lccn', []),
                    'oclcs': ids.get('oclc', []),
                    'olids': [ key_to_olid(data['key']) ],
                    'publishDates': [ data.get('publish_date', '') ],
                    'recordURL': data['url'],
                    'data': data,
                    'details', details,
                    } },
            'items': items }
        return result


    def process(self, req):
        requests = req.split('|')
        bib_keys = sum([r.split(';') for r in requests], [])

        # filter out 'id:foo' before passing to dynlinks
        bib_keys = [k for k in bib_keys if k[:3].lower() != 'id:']

        self.docs = dynlinks.query_docs(bib_keys)
        self.detailss = dynlinks.process_result_for_details(self.docs)
        dp = dynlinks.DataProcessor()
        self.datas = dp.process(self.docs)
        self.works = dp.works

        self.work_to_iaids = dict((workid, get_work_iaids(workid)) for workid in self.works)
        iaids = sum(self.work_to_iaids.values(), [])
        self.iaid_to_meta = dict((iaid, ia.get_meta_xml(iaid)) for iaid in iaids)
        self.iaid_to_ed_key = dict((iaid, ol_query('ocaid', iaid))
                                 for iaid in iaids)
        self.iaid_to_ed = dict((iaid, web.ctx.site.get(olkey))
                               for iaid, olkey in self.iaid_to_ed_key.items() if olkey)

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

        return result


def readlinks(req, options):
    try:
        result = ReadProcessor().process(req)
    except:
        print >> sys.stderr, "Error in processing Read API"
        register_exception()
        
        result = [] # XXX check for compatibility?
    return result
