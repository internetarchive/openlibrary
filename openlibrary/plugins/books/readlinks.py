""" 'Read' api implementation.  This is modeled after the HathiTrust
Bibliographic API, but also includes information about loans and other
editions of the same work that might be available.
"""

from openlibrary.core import inlibrary
from openlibrary.core import ia
from openlibrary.core import helpers
from openlibrary.api import OpenLibrary

import dynlinks
import web


def key_to_olid(olkey):
    return olkey.split('/')[-1]


ol = OpenLibrary("http://openlibrary.org")
def get_work_editions(work):
    editions = ol.query({ 'type': '/type/edition',
                          'works': work.key,
                          'limit': False })
    # return editions
    # return editions only if this ol knows about them.
    return [edition for edition in editions if web.ctx.site.get(edition)]


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

    raise Exception

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


def lookup(bibkey):
    bka = [bibkey]
    r = dynlinks.query_docs(bka)

    if len(r) == 0:
        return []

    record = r[bibkey]
    edition = web.ctx.site.get(record['key'])
    work = web.ctx.site.get(record['works'][0]['key']) # xxx

    user_inlibrary = inlibrary.get_library()

    # XXX fix
    thised_item = get_readable_edition_item(edition, work,
                                            user_inlibrary, edition)
    eds = get_work_editions(work)
    eds = [ed for ed in eds if ed != edition['key'].split('/')[-1]]

    # XXX turn this into a multi-get
    eds = [web.ctx.site.get(ed) for ed in eds]
    othered_items = [get_readable_edition_item(ed, work,
                                               user_inlibrary, edition)
                     for ed in eds]
    othered_items = [item for item in othered_items if item]
    if thised_item:
        othered_items.insert(0, thised_item)
    items = othered_items

    (data, details, viewapi) = [dynlinks.process_result(r, cmd)[bibkey]
                                for cmd in ('data', 'details', 'viewapi')]
    # return record, edition, work, eds, data, items

    isbns = edition.get('isbn_10', [])
    isbns.extend(edition.get('isbn_13', [])) # xxx ? how to handle.

    result = {'records':
                  { edition['key']:
                        { 'isbns': isbns,
                          'issns': [],
                          'lccns': edition.get('lccn', []),
                          'oclcs': edition.get('oclc_numbers', []),
                          'publishDates': [edition['publish_date']],
                          # XXX below openlibrary.org from conf
                          'recordURL': 'http://openlibrary.org%s' % edition['key'],
                          # 'marc-xml': ''
                          'data': data
                          } },
              'items': items }
    return result


def readlink_single(bibkey, options):
    return lookup(bibkey)


def readlink_multiple(bibkey_str, options):
    return 'hello multiple %s' % (bibkey_str)
