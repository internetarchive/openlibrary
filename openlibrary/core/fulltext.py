
import urllib
import urllib2
import simplejson
import logging

import web
from infogami import config
from openlibrary.core.lending import get_availability_of_ocaids

logger = logging.getLogger("openlibrary.inside")

def toc_search_api(q, page=1, limit=50):
    if not hasattr(config, 'plugin_inside'):
        return {'error': 'Unable to prepare search engine'}
    offset = (page - 1) * limit
    params = {
        'limit': limit,
        'q': q,
        'nofacets': 'true',
        'olonly': 'true',
        'fields': 'toc',
        'from': offset,
        'size': limit
    }

    toc_search_url = '%s?%s' % (
        config.toc_search['toc_endpoint'],
        urllib.urlencode(params, 'utf-8'))

    try:
        json_data = urllib2.urlopen(toc_search_url, timeout=30).read()
    except:
        return {'error': 'Unable to query toc search engine'}

    try:
        return simplejson.loads(json_data)
    except:
        return {
            'error': 'Error converting toc search engine data to JSON'
        }

def toc_search(q, page=1, limit=50):
    ia_results = toc_search_api(q, page=page, limit=limit)

    if 'error' not in ia_results and ia_results['hits']:
        hits = ia_results['hits'].get('hits', [])
        ocaids = [hit['_source'].get('meta_identifier', '') for hit in hits]
        availability = get_availability_of_ocaids(ocaids)                
        if 'error' in availability:
            return []
        editions = web.ctx.site.get_many([
            '/books/%s' % availability[ocaid].get('openlibrary_edition')
            for ocaid in availability
            if availability[ocaid].get('openlibrary_edition')])
        for ed in editions:
            idx = ocaids.index(ed.ocaid)
            ia_results['hits']['hits'][idx]['edition'] = ed
            ia_results['hits']['hits'][idx]['availability'] = availability[ed.ocaid]
    return ia_results


def fulltext_search_api(params):
    if not hasattr(config, 'plugin_inside'):
        return {'error': 'Unable to prepare search engine'}
    search_endpoint = config.plugin_inside['search_endpoint']
    search_select = search_endpoint + '?' + urllib.urlencode(params, 'utf-8')

    try:
        json_data = urllib2.urlopen(search_select, timeout=30).read()
        logger.debug('URL: ' + search_select)
    except:
        return {'error': 'Unable to query search engine'}

    try:
        return simplejson.loads(json_data)
    except:
        return {'error': 'Error converting search engine data to JSON'}


def fulltext_search(q, page=1, limit=100):
    offset = (page - 1) * limit
    ia_results = fulltext_search_api({
        'q': q, 'from': offset,
        'size': limit, 'olonly': 'true'
    })

    if 'error' not in ia_results and ia_results['hits']:
        hits = ia_results['hits'].get('hits', [])
        ocaids = [hit['fields'].get('identifier', [''])[0] for hit in hits]
        availability = get_availability_of_ocaids(ocaids)                
        if 'error' in availability:
            return []
        editions = web.ctx.site.get_many([
            '/books/%s' % availability[ocaid].get('openlibrary_edition')
            for ocaid in availability
            if availability[ocaid].get('openlibrary_edition')])
        for ed in editions:
            idx = ocaids.index(ed.ocaid)
            ia_results['hits']['hits'][idx]['edition'] = ed
            ia_results['hits']['hits'][idx]['availability'] = availability[ed.ocaid]
    return ia_results


