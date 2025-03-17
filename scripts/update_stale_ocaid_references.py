#!/usr/bin/env python3
"""
PYTHONPATH=. python ./scripts/update_dark_ocaid_references.py /olsystem/etc/openlibrary.yml --since "2025-03"

# e.g. https://openlibrary.org/recentchanges/2025/03/16/bulk_update/146351306
"""

import _init_path  # noqa: F401  Imported for its side effect of setting PYTHONPATH
import requests
import web
from typing import Optional

import infogami
from infogami import config
from openlibrary.accounts import RunAs
from openlibrary.config import load_config
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI


def get_dark_ol_editions(s3_keys, cursor=None, rows=1000, since=None, until=None):
    if not s3_keys or not all(k in s3_keys for k in ("s3_key", "s3_secret")):
        raise ValueError("Invalid S3 keys provided")
    scrape_api_url = "https://archive.org/services/search/v1/scrape"
    headers = {"authorization": "LOW {s3_key}:{s3_secret}".format(**s3_keys)}
    fields = ["identifier", "curatenote", "curatedate", "openlibrary_edition"]
    q = "openlibrary_edition:*"
    if since or until:
        q = ' AND '.join((q, f"curatedate:[{since or '*'} TO {until or '*'}]"))

    query_params = {
        "q": q,
        "count": rows,
        "scope": "dark",
        "service": "metadata__dark",
        "fields": ",".join(fields),
    }
    if cursor:
        query_params['cursor'] = cursor

    response = requests.get(scrape_api_url, headers=headers, params=query_params)
    response.raise_for_status()
    data = response.json()
    cursor = data.get("cursor")
    editions = {
        # Edition key `/books/OL123M` mapped to its ES dark item metadata
        f'/books/{doc["openlibrary_edition"]}': doc
        for doc in data.get("items", [])
    }
    return editions, cursor


def disassociate_dark_ocaids(s3_keys, since=None, until=None, test=True):
    cursor = ""
    editions_fetched, editions_dirty, editions_updated = (0, 0, 0)
    while cursor is not None:
        es_editions, cursor = get_dark_ol_editions(
            s3_keys, since=since, until=until, cursor=cursor
        )
        editions_fetched += len(es_editions)
        ol_editions = web.ctx.site.get_many(list(es_editions.keys()))
        updated_eds = []
        for ed in ol_editions:
            es_id = es_editions[ed.key]['identifier']
            ed_dict = ed.dict()
            if ed_dict.get('ocaid') and es_id == ed_dict['ocaid']:
                editions_dirty += 1
                del ed_dict['ocaid']
                updated_eds.append(ed_dict)
                print(f"Dirty: {ed.key}")

        if updated_eds and not test:
            editions_updated += len(updated_eds)
            with RunAs('ImportBot'):
                web.ctx.ip = web.ctx.ip or '127.0.0.1'
                web.ctx.site.save_many(updated_eds, comment="Redacting ocaids")
    return editions_fetched, editions_dirty, editions_updated


def main(ol_config: str, since: Optional[str] = None, until: Optional[str] = None, test: bool = True):
    load_config(ol_config)
    infogami._setup()
    s3_keys = config.get('ia_ol_metadata_write_s3')  # XXX needs dark scope
    editions_fetched, editions_dirty, editions_updated = disassociate_dark_ocaids(
        s3_keys, since=since, until=until, test=test
    )
    print(
        f"{editions_fetched} editions fetched, "
        f"{editions_dirty} editions dirty, "
        f"{editions_updated} editions updated"
    )


if __name__ == '__main__':
    FnToCLI(main).run()
