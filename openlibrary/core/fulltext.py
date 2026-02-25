import json
import logging
from urllib.parse import urlencode

import httpx

from infogami import config
from openlibrary.core.lending import get_availability
from openlibrary.plugins.openlibrary.home import format_book_data
from openlibrary.utils.async_utils import async_bridge
from openlibrary.utils.request_context import req_context, site_ctx

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
        "x-preferred-client-id": req_context.get().x_forwarded_for or "ol-internal",
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


async def fulltext_search_async(
    q, page=1, offset=None, limit=100, js=False, facets=False
):
    if offset is None:
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
            availability = {}

        edition_keys = list(
            site_ctx.things(
                {'type': '/type/edition', 'ocaid': ocaids, 'limit': len(ocaids)}
            )
        )
        editions = site_ctx.get_many(edition_keys)
        for ed in editions:
            idx = ocaids.index(ed.ocaid)
            hit = ia_results['hits']['hits'][idx]
            hit['edition'] = (
                format_book_data(ed, fetch_availability=False) if js else ed
            )
            hit['availability'] = availability.get(ed.ocaid, {})
    return ia_results


fulltext_search = async_bridge.wrap(fulltext_search_async)
