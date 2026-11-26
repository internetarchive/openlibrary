"""Search utilities."""

import logging
import os
from typing import Any
from urllib.parse import urlencode

import httpx

from infogami import config
from openlibrary.utils.async_utils import async_bridge
from openlibrary.utils.solr import DEFAULT_PASS_TIME_ALLOWED, DEFAULT_SOLR_TIMEOUT_SECONDS, Solr

logger = logging.getLogger("openlibrary.worksearch")

_ACTIVE_SOLR: Solr | None = None


def get_solr():
    global _ACTIVE_SOLR
    if not _ACTIVE_SOLR:
        if os.environ.get("OL_SOLR_BASE_URL"):
            base_url = os.environ["OL_SOLR_BASE_URL"]
        else:
            base_url = config.plugin_worksearch.get("solr_base_url")

        _ACTIVE_SOLR = Solr(base_url)
    return _ACTIVE_SOLR


async def execute_solr_query_async(
    solr_path: str,
    params: dict | list[tuple[str, Any]],
    _timeout: int | None = DEFAULT_SOLR_TIMEOUT_SECONDS,
    _pass_time_allowed: bool = DEFAULT_PASS_TIME_ALLOWED,
) -> httpx.Response | None:
    try:
        response = await get_solr().raw_request(
            solr_path,
            urlencode(params),
            _timeout=_timeout,
            _pass_time_allowed=_pass_time_allowed,
        )
    except httpx.HTTPError:
        logger.exception("Failed solr query")
        return None
    return response


execute_solr_query = async_bridge.wrap(execute_solr_query_async)
