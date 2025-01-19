import functools
import json
import logging
from pathlib import Path
from typing import Literal, cast

import aiofiles
import web

from openlibrary.catalog.utils.query import set_query_host
from openlibrary.solr.data_provider import (
    DataProvider,
    ExternalDataProvider,
    get_data_provider,
)
from openlibrary.solr.updater.abstract import AbstractSolrUpdater
from openlibrary.solr.updater.author import AuthorSolrUpdater
from openlibrary.solr.updater.edition import EditionSolrUpdater
from openlibrary.solr.updater.list import ListSolrUpdater
from openlibrary.solr.updater.work import WorkSolrUpdater
from openlibrary.solr.utils import (
    SolrUpdateRequest,
    load_config,
    set_solr_base_url,
    set_solr_next,
    solr_update,
)
from openlibrary.utils import uniq
from openlibrary.utils.open_syllabus_project import set_osp_dump_location

logger = logging.getLogger("openlibrary.solr")


# This will be set to a data provider; have faith, mypy!
data_provider = cast(DataProvider, None)


@functools.cache
def get_solr_updaters() -> list[AbstractSolrUpdater]:
    assert data_provider is not None
    return [
        # ORDER MATTERS
        EditionSolrUpdater(data_provider),
        WorkSolrUpdater(data_provider),
        AuthorSolrUpdater(data_provider),
        ListSolrUpdater(data_provider),
    ]


def can_update_key(key: str) -> bool:
    return any(updater.key_test(key) for updater in get_solr_updaters())


async def update_keys(
    keys: list[str],
    commit=True,
    output_file=None,
    skip_id_check=False,
    update: Literal['update', 'print', 'pprint', 'quiet'] = 'update',
) -> SolrUpdateRequest:
    """
    Insert/update the documents with the provided keys in Solr.

    :param list[str] keys: Keys to update (ex: ["/books/OL1M"]).
    :param bool commit: Create <commit> tags to make Solr persist the changes (and make the public/searchable).
    :param str output_file: If specified, will save all update actions to output_file **instead** of sending to Solr.
        Each line will be JSON object.
        FIXME Updates to editions/subjects ignore output_file and will be sent (only) to Solr regardless.
    """
    logger.debug("BEGIN update_keys")

    def _solr_update(update_state: SolrUpdateRequest):
        if update == 'update':
            return solr_update(update_state, skip_id_check)
        elif update == 'pprint':
            print(update_state.to_solr_requests_json(sep='\n', indent=4))
        elif update == 'print':
            print(update_state.to_solr_requests_json(sep='\n'))
        elif update == 'quiet':
            pass

    global data_provider
    if data_provider is None:
        data_provider = get_data_provider('default')

    net_update = SolrUpdateRequest(commit=commit)

    for updater in get_solr_updaters():
        update_state = SolrUpdateRequest(commit=commit)
        updater_keys = uniq(k for k in keys if updater.key_test(k))
        await updater.preload_keys(updater_keys)
        for key in updater_keys:
            logger.debug(f"processing {key}")
            try:
                thing = await data_provider.get_document(key)

                if thing and thing['type']['key'] == '/type/redirect':
                    logger.warning("Found redirect to %r", thing['location'])
                    # When the given key is not found or redirects to another thing,
                    # explicitly delete the key. It won't get deleted otherwise.
                    update_state.deletes.append(thing['key'])
                    thing = await data_provider.get_document(thing['location'])

                if not thing:
                    logger.warning("No thing found for key %r. Ignoring...", key)
                    continue
                if thing['type']['key'] == '/type/delete':
                    logger.info(
                        "%r has type %r. queuing for deleting it solr.",
                        thing['key'],
                        thing['type']['key'],
                    )
                    update_state.deletes.append(thing['key'])
                else:
                    new_update_state, new_keys = await updater.update_key(thing)
                    update_state += new_update_state
                    keys += new_keys
            except:  # noqa: E722
                logger.error("Failed to update %r", key, exc_info=True)

        if update_state.has_changes():
            if output_file:
                async with aiofiles.open(output_file, "w") as f:
                    for doc in update_state.adds:
                        await f.write(f"{json.dumps(doc)}\n")
            else:
                _solr_update(update_state)
        net_update += update_state

    logger.debug("END update_keys")
    return net_update


async def do_updates(keys):
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )
    await update_keys(keys, commit=False)


def load_configs(
    c_host: str,
    c_config: str,
    c_data_provider: (
        DataProvider | Literal["default", "legacy", "external"]
    ) = 'default',
) -> DataProvider:
    host = web.lstrips(c_host, "http://").strip("/")
    set_query_host(host)

    load_config(c_config)

    global data_provider
    if data_provider is None:
        if isinstance(c_data_provider, DataProvider):
            data_provider = c_data_provider
        elif c_data_provider == 'external':
            data_provider = ExternalDataProvider(host)
        else:
            data_provider = get_data_provider(c_data_provider)
    return data_provider


async def main(
    keys: list[str],
    osp_dump: Path | None = None,
    ol_url="http://openlibrary.org",
    ol_config="openlibrary.yml",
    output_file: str | None = None,
    commit=True,
    data_provider: Literal['default', 'legacy', 'external'] = "default",
    solr_base: str | None = None,
    solr_next=False,
    update: Literal['update', 'print', 'pprint'] = 'update',
):
    """
    Insert the documents with the given keys into Solr.

    :param keys: The keys of the items to update (ex: /books/OL1M)
    :param ol_url: URL of the openlibrary website
    :param ol_config: Open Library config file
    :param output_file: Where to save output
    :param commit: Whether to also trigger a Solr commit
    :param data_provider: Name of the data provider to use
    :param solr_base: If wanting to override openlibrary.yml
    :param solr_next: Whether to assume schema of next solr version is active
    :param update: Whether/how to do the actual solr update call
    """
    load_configs(ol_url, ol_config, data_provider)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )

    if keys[0].startswith('//'):
        keys = [k[1:] for k in keys]

    if solr_base:
        set_solr_base_url(solr_base)

    set_solr_next(solr_next)
    set_osp_dump_location(osp_dump)

    await update_keys(keys, commit=commit, output_file=output_file, update=update)


if __name__ == '__main__':
    from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

    FnToCLI(main).run()
