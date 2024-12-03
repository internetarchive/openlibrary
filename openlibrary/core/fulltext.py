import json
import logging
from urllib.parse import urlencode

import requests
import web

from infogami import config
from openlibrary.core.lending import get_availability_of_ocaids
from openlibrary.plugins.openlibrary.home import format_book_data

logger = logging.getLogger("openlibrary.inside")


def fulltext_search_api(params):
    if not hasattr(config, 'plugin_inside'):
        return {'error': 'Unable to prepare search engine'}
    search_endpoint = config.plugin_inside['search_endpoint']
    search_select = search_endpoint + '?' + urlencode(params, 'utf-8')

    logger.debug('URL: ' + search_select)
    try:
        response = requests.get(search_select, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.HTTPError:
        return {'error': 'Unable to query search engine'}
    except json.decoder.JSONDecodeError:
        return {'error': 'Error converting search engine data to JSON'}


def fulltext_search(q, page=1, limit=100, js=False, facets=False):
    offset = (page - 1) * limit
    params = {
        'q': q,
        'from': offset,
        'size': limit,
        **({'nofacets': 'true'} if not facets else {}),
        'olonly': 'true',
    }
    ia_results = fulltext_search_api(params)

    if 'error' not in ia_results and ia_results['hits']:
        hits = ia_results['hits'].get('hits', [])
        ocaids = [hit['fields'].get('identifier', [''])[0] for hit in hits]
        availability = get_availability_of_ocaids(ocaids)
        if 'error' in availability:
            return []
        editions = web.ctx.site.get_many(
            [
                '/books/%s' % availability[ocaid].get('openlibrary_edition')
                for ocaid in availability
                if availability[ocaid].get('openlibrary_edition')
            ]
        )
        for ed in editions:
            if ed.ocaid in ocaids:
                idx = ocaids.index(ed.ocaid)
                ia_results['hits']['hits'][idx]['edition'] = (
                    format_book_data(ed, fetch_availability=False) if js else ed
                )
                ia_results['hits']['hits'][idx]['availability'] = availability[ed.ocaid]
    return ia_results
