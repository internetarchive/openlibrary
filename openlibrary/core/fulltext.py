import logging
import json
import requests
import web
from infogami import config
from openlibrary.core.lending import get_availability_of_ocaids


def fulltext_search_api(params):
    if not hasattr(config, 'plugin_inside'):
        return {'error': 'Unable to prepare search engine'}
    search_endpoint = config.plugin_inside['search_endpoint']

    try:
        response = requests.get(search_endpoint, params=params, timeout=30)
        try:
            logger = logging.getLogger("openlibrary.inside")
            logger.debug('base URL: ' + search_endpoint)
            logger.debug('query parameters: ' + str(params))
            return response.json()
        except json.decoder.JSONDecodeError:
            return {'error': 'Error converting search engine data to JSON'}

    except:
        return {'error': 'Unable to query search engine'}

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
            if ed.ocaid in ocaids:
                idx = ocaids.index(ed.ocaid)
                ia_results['hits']['hits'][idx]['edition'] = ed
                ia_results['hits']['hits'][idx]['availability'] = availability[ed.ocaid]
    return ia_results


