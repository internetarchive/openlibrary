import json
import logging
from urllib.parse import urlencode

import httpx

from infogami import config
from openlibrary.core.lending import get_availability
from openlibrary.plugins.openlibrary.home import format_book_data
from openlibrary.utils import async_utils
from openlibrary.utils.async_utils import async_bridge, x_forwarded_for

logger = logging.getLogger("openlibrary.inside")


async def fulltext_search_api(params):
    from openlibrary.core.lending import (
        config_fts_context,
        config_ia_ol_metadata_write_s3,
    )

    if not hasattr(config, 'plugin_inside'):
        return {'error': 'Unable to prepare search engine'}
    search_endpoint = config.plugin_inside['search_endpoint']
    search_select = search_endpoint + '?' + urlencode(params, 'utf-8')
    headers = {
        "x-preferred-client-id": x_forwarded_for.get(),
        "x-application-id": "openlibrary",
    }
    if config_fts_context is not None:
        headers["x-search-request-context"] = config_fts_context
    if config_ia_ol_metadata_write_s3:
        headers["authorization"] = "LOW {s3_key}:{s3_secret}".format(
            **config_ia_ol_metadata_write_s3
        )

    logger.debug('URL: ' + search_select)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(search_select, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError:
        return {'error': 'Unable to query search engine'}
    except json.decoder.JSONDecodeError:
        return {'error': 'Error converting search engine data to JSON'}


async def fulltext_search_async(q, page=1, limit=100, js=False, facets=False):
    offset = (page - 1) * limit
    params = {
        'q': q,
        'from': offset,
        'size': limit,
        **({'nofacets': 'true'} if not facets else {}),
        'olonly': 'true',
    }
    ia_results = await fulltext_search_api(params)

    if 'error' not in ia_results and ia_results['hits']:
        hits = ia_results['hits'].get('hits', [])
        ocaids = [hit['fields'].get('identifier', [''])[0] for hit in hits]
        availability = get_availability('identifier', ocaids)
        if 'error' in availability:
            return {"hits": {"hits": []}}
        editions = async_utils.site.get().get_many(
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


fulltext_search = async_bridge.wrap(fulltext_search_async)
