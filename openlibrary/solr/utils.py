from __future__ import annotations
import json
import logging
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

import httpx
from httpx import HTTPError, HTTPStatusError, TimeoutException

from openlibrary import config
from openlibrary.utils.retry import MaxRetriesExceeded, RetryStrategy

if TYPE_CHECKING:
    from openlibrary.solr.solr_types import SolrDocument

logger = logging.getLogger("openlibrary.solr")


solr_base_url = None
solr_next: bool | None = None
httpx_client = httpx.AsyncClient()


def load_config(c_config="conf/openlibrary.yml"):
    if not config.runtime_config:
        config.load(c_config)
        config.load_config(c_config)


def get_solr_base_url():
    """
    Get Solr host

    :rtype: str
    """
    global solr_base_url

    if solr_base_url is not None:
        return solr_base_url

    if os.environ.get("OL_SOLR_BASE_URL"):
        solr_base_url = os.environ["OL_SOLR_BASE_URL"]
    else:
        load_config()
        solr_base_url = config.runtime_config["plugin_worksearch"]["solr_base_url"]

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
        if env_val := os.environ.get("OL_SOLR_NEXT"):
            if env_val not in ("true", "false", ""):
                raise ValueError(f"Invalid OL_SOLR_NEXT, got {env_val}")
            solr_next = env_val == "true"
        else:
            load_config()
            solr_next = cast(bool, config.runtime_config["plugin_worksearch"].get("solr_next", False))

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

    def to_solr_requests_json(self, indent: int | str | None = None, sep=",") -> str:
        result = "{"
        if self.deletes:
            result += f'"delete": {json.dumps(self.deletes, indent=indent)}' + sep
        for doc in self.adds:
            result += f'"add": {json.dumps({"doc": doc}, indent=indent)}' + sep
        if self.commit:
            result += '"commit": {}' + sep

        result = result.removesuffix(sep)
        result += "}"
        return result

    def clear_requests(self) -> None:
        self.adds.clear()
        self.deletes.clear()


async def solr_update(
    update_request: SolrUpdateRequest,
    skip_id_check=False,
    solr_base_url: str | None = None,
) -> None:
    content = update_request.to_solr_requests_json()

    solr_base_url = solr_base_url or get_solr_base_url()
    params = {
        # Don't fail the whole batch if one bad apple
        "update.chain": "tolerant-chain"
    }
    if skip_id_check:
        params["overwrite"] = "false"

    async def make_request():
        logger.debug(f"POSTing update to {solr_base_url}/update {params}")
        try:
            resp = await httpx_client.post(
                f"{solr_base_url}/update",
                # Large batches especially can take a decent chunk of time
                timeout=300,
                params=params,
                headers={"Content-Type": "application/json"},
                content=content,
            )

            if resp.status_code in (200, 400):
                resp_json = resp.json()

                if indiv_errors := resp_json.get("responseHeader", {}).get("errors", []):
                    for e in indiv_errors:
                        logger.error(f"Individual Solr POST Error: {e}")

                if global_error := resp_json.get("error"):
                    logger.error(f"Global Solr POST Error: {global_error.get('msg')}")

                if not indiv_errors and not global_error:
                    resp.raise_for_status()
            else:
                resp.raise_for_status()

        except HTTPStatusError as e:
            logger.error(f"HTTP Status Solr POST Error: {e}")
            raise
        except TimeoutException:
            logger.error(f"Timeout Solr POST Error: {content}")
            raise
        except HTTPError as e:
            logger.error(f"HTTP Solr POST Error: {e}")
            raise

    retry = RetryStrategy(
        [HTTPStatusError, TimeoutException, HTTPError],
        max_retries=5,
        delay=8,
    )

    try:
        return await retry.async_call(make_request)
    except MaxRetriesExceeded as e:
        logger.error(f"Max retries exceeded for Solr POST: {e.last_exception}")


async def solr_insert_documents(
    documents: list[dict],
    solr_base_url: str | None = None,
    skip_id_check=False,
    tolerant_chain=False,
    timeout: float | None = 30,  # noqa: ASYNC109
):
    """
    :param documents: List of documents to insert into Solr
    :param solr_base_url: Base URL for Solr, e.g. http://localhost:8983/solr/openlibrary
    :param skip_id_check: DANGER! If true, Solr will not check for duplicate IDs and will
    insert documents even if they have the same ID as an existing document. This can lead
        to data corruption and should only be used if you are sure that there are no
        duplicate IDs in your dataset -- e.g. when inserting into an empty solr.
    :param tolerant_chain: If true, use Solr's tolerant update chain, which will allow
        the update to succeed even if some documents fail to index. This is useful for
        large batches where you want to maximize the number of documents that get indexed,
        even if there are some bad apples in the batch.
    """
    solr_base_url = solr_base_url or get_solr_base_url()
    params = {}
    if skip_id_check:
        params["overwrite"] = "false"
    if tolerant_chain:
        params["update.chain"] = "tolerant-chain"
    logger.debug(f"POSTing update to {solr_base_url}/update {params}")
    try:
        resp = await httpx_client.post(
            f"{solr_base_url}/update",
            timeout=timeout,
            params=params,
            headers={"Content-Type": "application/json"},
            content=json.dumps(documents),
        )
        resp.raise_for_status()
    except HTTPStatusError as e:
        response_body = e.response.text if e.response is not None else None
        logger.error(f"HTTP Status Solr POST Error: {e}; response body: {response_body}")
        raise
