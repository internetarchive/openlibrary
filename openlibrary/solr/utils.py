import json
import logging
from dataclasses import dataclass, field

import httpx
from httpx import HTTPError, HTTPStatusError, TimeoutException

from openlibrary import config
from openlibrary.solr.solr_types import SolrDocument
from openlibrary.utils.retry import MaxRetriesExceeded, RetryStrategy

logger = logging.getLogger("openlibrary.solr")


solr_base_url = None
solr_next: bool | None = None


def load_config(c_config='conf/openlibrary.yml'):
    if not config.runtime_config:
        config.load(c_config)
        config.load_config(c_config)


def get_solr_base_url():
    """
    Get Solr host

    :rtype: str
    """
    global solr_base_url

    load_config()

    if not solr_base_url:
        solr_base_url = config.runtime_config['plugin_worksearch']['solr_base_url']

    return solr_base_url


def set_solr_base_url(solr_url: str):
    global solr_base_url
    solr_base_url = solr_url


def get_solr_next() -> bool:
    """
    Get whether this is the next version of solr; ie new schema configs/fields, etc.
    """
    global solr_next

    if solr_next is None:
        load_config()
        solr_next = config.runtime_config['plugin_worksearch'].get('solr_next', False)

    return solr_next


def set_solr_next(val: bool):
    global solr_next
    solr_next = val


@dataclass
class SolrUpdateRequest:
    adds: list[SolrDocument] = field(default_factory=list)
    """Records to be added/modified"""

    deletes: list[str] = field(default_factory=list)
    """Records to be deleted"""

    commit: bool = False

    # Override the + operator
    def __add__(self, other):
        if isinstance(other, SolrUpdateRequest):
            return SolrUpdateRequest(
                adds=self.adds + other.adds,
                deletes=self.deletes + other.deletes,
                commit=self.commit or other.commit,
            )
        else:
            raise TypeError(f"Cannot add {type(self)} and {type(other)}")

    def has_changes(self) -> bool:
        return bool(self.adds or self.deletes)

    def to_solr_requests_json(self, indent: int | str | None = None, sep=',') -> str:
        result = '{'
        if self.deletes:
            result += f'"delete": {json.dumps(self.deletes, indent=indent)}' + sep
        for doc in self.adds:
            result += f'"add": {json.dumps({"doc": doc}, indent=indent)}' + sep
        if self.commit:
            result += '"commit": {}' + sep

        if result.endswith(sep):
            result = result[: -len(sep)]
        result += '}'
        return result

    def clear_requests(self) -> None:
        self.adds.clear()
        self.deletes.clear()


def solr_update(
    update_request: SolrUpdateRequest,
    skip_id_check=False,
    solr_base_url: str | None = None,
) -> None:
    content = update_request.to_solr_requests_json()

    solr_base_url = solr_base_url or get_solr_base_url()
    params = {
        # Don't fail the whole batch if one bad apple
        'update.chain': 'tolerant-chain'
    }
    if skip_id_check:
        params['overwrite'] = 'false'

    def make_request():
        logger.debug(f"POSTing update to {solr_base_url}/update {params}")
        try:
            resp = httpx.post(
                f'{solr_base_url}/update',
                # Large batches especially can take a decent chunk of time
                timeout=300,
                params=params,
                headers={'Content-Type': 'application/json'},
                content=content,
            )

            if resp.status_code == 400:
                resp_json = resp.json()

                indiv_errors = resp_json.get('responseHeader', {}).get('errors', [])
                if indiv_errors:
                    for e in indiv_errors:
                        logger.error(f'Individual Solr POST Error: {e}')

                global_error = resp_json.get('error')
                if global_error:
                    logger.error(f'Global Solr POST Error: {global_error.get("msg")}')

                if not (indiv_errors or global_error):
                    # We can handle the above errors. Any other 400 status codes
                    # are fatal and should cause a retry
                    resp.raise_for_status()
            else:
                resp.raise_for_status()
        except HTTPStatusError as e:
            logger.error(f'HTTP Status Solr POST Error: {e}')
            raise
        except TimeoutException:
            logger.error(f'Timeout Solr POST Error: {content}')
            raise
        except HTTPError as e:
            logger.error(f'HTTP Solr POST Error: {e}')
            raise

    retry = RetryStrategy(
        [HTTPStatusError, TimeoutException, HTTPError],
        max_retries=5,
        delay=8,
    )

    try:
        return retry(make_request)
    except MaxRetriesExceeded as e:
        logger.error(f'Max retries exceeded for Solr POST: {e.last_exception}')


async def solr_insert_documents(
    documents: list[dict],
    solr_base_url: str | None = None,
    skip_id_check=False,
):
    """
    Note: This has only been tested with Solr 8, but might work with Solr 3 as well.
    """
    solr_base_url = solr_base_url or get_solr_base_url()
    params = {}
    if skip_id_check:
        params['overwrite'] = 'false'
    logger.debug(f"POSTing update to {solr_base_url}/update {params}")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f'{solr_base_url}/update',
            timeout=30,  # seconds; the default timeout is silly short
            params=params,
            headers={'Content-Type': 'application/json'},
            content=json.dumps(documents),
        )
    resp.raise_for_status()


def str_to_key(s):
    """
    Convert a string to a valid Solr field name.
    TODO: this exists in openlibrary/utils/__init__.py str_to_key(), DRY
    :param str s:
    :rtype: str
    """
    to_drop = set(''';/?:@&=+$,<>#%"{}|\\^[]`\n\r''')
    return ''.join(c if c != ' ' else '_' for c in s.lower() if c not in to_drop)
