import logging
import re

import requests
from openlibrary.solr.updater.abstract import AbstractSolrUpdater
from openlibrary.solr.utils import SolrUpdateRequest, get_solr_base_url

logger = logging.getLogger("openlibrary.solr")
re_edition_key_basename = re.compile("^[a-zA-Z0-9:.-]+$")


class EditionSolrUpdater(AbstractSolrUpdater):
    key_prefix = '/books/'
    thing_type = '/type/edition'

    async def update_key(self, thing: dict) -> tuple[SolrUpdateRequest, list[str]]:
        update = SolrUpdateRequest()
        new_keys: list[str] = []
        if thing['type']['key'] == self.thing_type:
            if thing.get("works"):
                new_keys.append(thing["works"][0]['key'])
                # Make sure we remove any fake works created from orphaned editions
                new_keys.append(thing['key'].replace('/books/', '/works/'))
            else:
                # index the edition as it does not belong to any work
                new_keys.append(thing['key'].replace('/books/', '/works/'))
        else:
            logger.info(
                "%r is a document of type %r. Checking if any work has it as edition in solr...",
                thing['key'],
                thing['type']['key'],
            )
            work_key = solr_select_work(thing['key'])
            if work_key:
                logger.info("found %r, updating it...", work_key)
                new_keys.append(work_key)
        return update, new_keys


def solr_select_work(edition_key):
    """
    Get corresponding work key for given edition key in Solr.

    :param str edition_key: (ex: /books/OL1M)
    :return: work_key
    :rtype: str or None
    """
    # solr only uses the last part as edition_key
    edition_key = edition_key.split("/")[-1]

    if not re_edition_key_basename.match(edition_key):
        return None

    edition_key = solr_escape(edition_key)
    reply = requests.get(
        f'{get_solr_base_url()}/select',
        params={
            'wt': 'json',
            'q': f'edition_key:{edition_key}',
            'rows': 1,
            'fl': 'key',
        },
    ).json()
    if docs := reply['response'].get('docs', []):
        return docs[0]['key']  # /works/ prefix is in solr


def solr_escape(query):
    """
    Escape special characters in Solr query.

    :param str query:
    :rtype: str
    """
    return re.sub(r'([\s\-+!()|&{}\[\]^"~*?:\\])', r'\\\1', query)
