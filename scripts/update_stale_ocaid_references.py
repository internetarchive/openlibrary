#!/usr/bin/env python3
"""
PYTHONPATH=. python ./scripts/update_stale_ocaid_references.py /olsystem/etc/openlibrary.yml --since "2025-03" --statefile "statefile.json"

# e.g. https://openlibrary.org/recentchanges/2025/03/16/bulk_update/146351306
"""

import json
import logging
import os
from itertools import batched

import _init_path  # noqa: F401  Imported for its side effect of setting PYTHONPATH
import requests
import web

# Import necessary components for advanced retries
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry  # Correct import path

import infogami
from infogami import config
from openlibrary.accounts import RunAs
from openlibrary.config import load_config
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

# Configure logging
logging.basicConfig(
    level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s'
)


def create_session_with_retries(
    total_retries=5,
    backoff_factor=1,
    status_forcelist=(500, 502, 503, 504),  # Common server errors
):
    """Creates a requests Session configured with automatic retries."""
    session = requests.Session()
    retry_strategy = Retry(
        total=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=[
            "HEAD",
            "GET",
            "OPTIONS",
        ],  # Use allowed_methods instead of deprecated method_whitelist
    )
    # Mount the adapter with the retry strategy to handle HTTP and HTTPS
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def get_dark_ol_editions(s3_keys, rows=10_000, since=None, until=None, statefile=None):
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

    # Create a session with configured retries
    session = create_session_with_retries(total_retries=5, backoff_factor=1)

    batch = 1
    cursor = ""
    editions = {}
    while cursor is not None:
        if cursor:
            query_params['cursor'] = cursor

        response = session.get(
            scrape_api_url, headers=headers, params=query_params, timeout=60
        )
        response.raise_for_status()
        data = response.json()
        cursor = data.get("cursor")
        editions.update(
            {
                # Edition key `/books/OL123M` mapped to its ES dark item metadata
                f'/books/{doc["openlibrary_edition"]}': doc
                for doc in data.get("items", [])
            }
        )
        print(
            f"Fetching batch {batch}; adding {len(data.get("items", []))} items -> {len(editions)}"
        )
        batch += 1
    if statefile:
        with open(statefile, 'w') as fout:
            json.dump(editions, fout)
    return editions


def disassociate_dark_ocaids(s3_keys, es_editions, test=True):
    counts = {
        "processed": 0,
        "dirty": 0,
        "updated": 0,
        "batches": 0,
        "total": len(es_editions),
    }

    edition_keys = list(es_editions.keys())

    # Process ocaids in batches of 1000
    BATCH_SIZE = 1_000
    for batch_keys in batched(edition_keys, BATCH_SIZE):
        ol_editions = web.ctx.site.get_many(list(batch_keys))

        updated_eds = []
        for ed in ol_editions:
            counts["processed"] += 1
            es_id = es_editions[ed.key]['identifier']
            ed_dict = ed.dict()
            if ed_dict.get('ocaid') == es_id:
                counts["dirty"] += 1
                del ed_dict['ocaid']
                updated_eds.append(ed_dict)

        if updated_eds and not test:
            counts["updated"] += len(updated_eds)
            with RunAs('ImportBot'):
                web.ctx.ip = web.ctx.ip or '127.0.0.1'
                web.ctx.site.save_many(updated_eds, comment="Redacting ocaids")
        print(counts)
        counts["batches"] += 1
    return counts


def main(
    ol_config: str,
    since: str | None = None,
    until: str | None = None,
    statefile: str | None = None,
    test: bool = True,
):
    load_config(ol_config)
    infogami._setup()
    s3_keys = config.get('ia_ol_metadata_write_s3')  # XXX needs dark scope
    if statefile and os.path.exists(statefile):
        with open(statefile) as fin:
            es_editions = json.load(fin)
    else:
        es_editions = get_dark_ol_editions(
            s3_keys, since=since, until=until, statefile=statefile
        )
    counts = disassociate_dark_ocaids(s3_keys, es_editions, test=test)
    print(counts)


if __name__ == '__main__':
    FnToCLI(main).run()
