#!/usr/bin/env python3
"""
See colab:
https://colab.research.google.com/drive/1HETHnP9bCS7zgli6YU32z5dWzlq0F1sY?authuser=2#scrollTo=7xd5NY4f_4pd

PYTHONPATH=. python ./scripts/bulk_load_ia_query.py /olsystem/etc/openlibrary.yml --idfile "ids.json" --no-test
"""


import _init_path  # noqa: F401  Imported for its side effect of setting PYTHONPATH
import datetime
import json
import logging
import os
import time # Keep for potential non-retry delays if needed, but not for backoff
import requests
import web
from requests.exceptions import RequestException
# Import necessary components for advanced retries
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry # Correct import path

import infogami
from infogami import config
from openlibrary.accounts import RunAs
from openlibrary.config import load_config
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

import importlib.util
spec = importlib.util.spec_from_file_location("openlibrary", "scripts/manage-imports.py")
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)


def create_session_with_retries(
    total_retries=5,
    backoff_factor=1,
    status_forcelist=(500, 502, 503, 504), # Common server errors
    allowed_methods=["HEAD", "GET", "OPTIONS"] # Methods to retry
):
    """Creates a requests Session configured with automatic retries."""
    session = requests.Session()
    retry_strategy = Retry(
        total=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=allowed_methods # Use allowed_methods instead of deprecated method_whitelist
    )
    # Mount the adapter with the retry strategy to handle HTTP and HTTPS
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def get_candidate_ocaids(s3_keys, rows=10_000, idfile=None):
    if not s3_keys or not all(k in s3_keys for k in ("s3_key", "s3_secret")):
        raise ValueError("Invalid S3 keys provided")
    scrape_api_url = "https://archive.org/services/search/v1/scrape"
    headers = {"authorization": "LOW {s3_key}:{s3_secret}".format(**s3_keys)}
    fields = ["identifier"]
    q = 'mediatype:texts AND format:pdf AND date:* AND title:* AND scanningcenter:* AND -volume:* AND -issn:* AND (imagecount:[20 TO 9999] OR isbn:*) AND -source:folio AND (-title:*report OR -isbn:*) AND -publisher:"[n.p.]" AND -title:"journal of" AND -title:"guo jia ke ji" AND -title:(paper* AND on) AND -title:(paper* AND from) AND -title:(lette* to) AND -title:(lette* from) AND -title:(handbook AND congress) AND -title:(transactions AND congress) AND -title:(proceeding OR proceedings OR *报告* OR *任务书 OR *年度* OR isbn* OR catalog OR catalogue OR cataloging OR *nknown OR supplementary OR records OR announcement OR dissertation) AND -collection:(opensource OR additional_collections OR dlarc OR larc OR spiritualfrontiersarchive OR fedlink OR newmannumismatic OR medicalofficerofhealthreports OR uoftgovpubs OR *ewspape* OR *amphle* OR microfi* OR Logboo* OR *earboo* OR *eriodica* OR *ocumen* OR *agazin* OR serial* OR *ovdoc* OR *vertis* OR posters* OR Personnel*) AND -subjects:(*ewspape* OR *amphle* OR microfi* OR Logboo* OR *earboo* OR *eriodica* OR *ocumen* OR *agazin* OR serial* OR *ovdoc* OR *vertis* OR posters* OR Personnel*) AND -creators:(*ewspape* OR *amphle* OR microfi* OR Logboo* OR *earboo* OR *eriodica* OR *ocumen* OR *agazin* OR serial* OR *ovdoc* OR *vertis* OR posters* OR Personnel*)' 

    query_params = {
        "q": q,
        "count": rows,
        "scope": "printdisabled",
        "fields": ",".join(fields),
    }

    # Create a session with configured retries
    session = create_session_with_retries(total_retries=5, backoff_factor=1)

    batch = 1
    cursor = ""
    ids = []
    while cursor is not None:
        if cursor:
            query_params['cursor'] = cursor

        response = session.get(scrape_api_url, headers=headers, params=query_params, timeout=60)
        response.raise_for_status()
        data = response.json()
        cursor = data.get("cursor")
        ids += [doc['identifier'] for doc in data.get("items", [])]
        print(f"Fetching batch {batch}; adding {len(data.get('items', []))} items -> {len(ids)}")
        batch += 1
    if idfile:
        with open(idfile, 'w') as fout:
            json.dump(ids, fout)
    return ids

def import_ocaids(ocaids, batch_size=5_000):
    # get the month for yesterday
    date = datetime.date.today() - datetime.timedelta(days=1)
    batch_name = f"new-scans-{date.year:04}{date.month:02}"
    batch = importer.Batch.find(batch_name) or importer.Batch.new(batch_name)

    for i in range(0, len(ocaids), batch_size):
        items = ocaids[i:i+batch_size]
        batch.add_items(items)

def main(
    ol_config: str,
    idfile: str | None = None,
    test: bool = True,
):
    load_config(ol_config)
    infogami._setup()
    s3_keys = config.get('ia_ol_metadata_write_s3')
    if idfile and os.path.exists(idfile):
        with open(idfile) as fin:
            ocaids = json.load(fin)
    else:
        ocaids = get_candidate_ocaids(s3_keys, idfile=idfile)

    if not test:
        import_ocaids(ocaids)
        
if __name__ == '__main__':
    FnToCLI(main).run()
