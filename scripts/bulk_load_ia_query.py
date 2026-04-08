#!/usr/bin/env python3
"""
See colab:
https://colab.research.google.com/drive/1HETHnP9bCS7zgli6YU32z5dWzlq0F1sY?authuser=2#scrollTo=7xd5NY4f_4pd

PYTHONPATH=. python ./scripts/bulk_load_ia_query.py /olsystem/etc/openlibrary.yml --idfile "ids.json" --no-test
"""

import datetime
import importlib.util
import json
import os
from itertools import batched

import _init_path  # noqa: F401  Imported for its side effect of setting PYTHONPATH
import requests

# Import necessary components for advanced retries
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry  # Correct import path

import infogami
from infogami import config
from openlibrary.config import load_config
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

spec = importlib.util.spec_from_file_location(
    "openlibrary", "scripts/manage-imports.py"
)
assert spec
importer = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(importer)

REQUIRED_FIELDS = [
    "mediatype:texts",
    "format:pdf",
    "date:*",
    "title:*",
    "scanningcenter:*",
    "-volume:*",
    "-issn:*",
    "(imagecount:[20 TO 9999] OR isbn:*)",
    "-source:folio",
]
SPECIAL_CASES = ["(-title:*report OR -isbn:*)", '-publisher:"[n.p.]"']
EXCLUDE_TITLES = [
    ' OR '.join(  # noqa: FLY002
        [
            "annals",
            "proceeding",
            "proceedings",
            "*报告*",
            "*任务书",
            "*年度*",
            "isbn*",
            "catalog",
            "catalogue",
            "cataloging",
            "*nknown",  # codespell:ignore
            "supplementary",
            "records",
            "announcement",
            "dissertation",
        ]
    )
]

EXCLUDE_COMPLEX_TITLES = [
    ' AND '.join(
        [
            f"-title:{t}"
            for t in [
                '"journal of"',
                '"guo jia ke ji"',
                "(paper* AND on)",
                "(paper* AND from)",
                "(lette* to)",
                "(lette* from)",
                "(handbook AND congress)",
                "(transactions AND congress)",
            ]
        ]
    )
]

ELIGIBLE_COLLECTIONS = [
    "internetarchivebooks",
    "toronto",
    "europeanlibraries",
    "americana",
    "inlibrary",
    "printdisabled",
]

EXCLUDE_GENERAL = [
    "*ewspape*",
    "*amphle*",
    "microfi*",
    "Logboo*",
    "*earboo*",
    "*eriodica*",
    "*ocumen*",
    "*agazin*",
    "serial*",
    "*ovdoc*",
    "*vertis*",
    "posters*",
    "Personnel*",
]

EXCLUDE_COLLECTIONS = [
    "opensource",
    "additional_collections",
    "dlarc",
    "larc",
    "spiritualfrontiersarchive",
    "fedlink",
    "newmannumismatic",
    "medicalofficerofhealthreports",
    "uoftgovpubs",
] + EXCLUDE_GENERAL

EXCLUDE_CREATORS = ["*ongres*", "u.s. mint", "国家", "(united AND states)"]


def create_session_with_retries(
    total_retries=5,
    backoff_factor=1,
    status_forcelist=(500, 502, 503, 504),  # Common server errors
    allowed_methods=("HEAD", "GET", "OPTIONS"),  # Methods to retry
):
    """Creates a requests Session configured with automatic retries."""
    session = requests.Session()
    retry_strategy = Retry(
        total=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=allowed_methods,  # Use allowed_methods instead of deprecated method_whitelist
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
    q = ' AND '.join(
        REQUIRED_FIELDS
        + SPECIAL_CASES
        + EXCLUDE_COMPLEX_TITLES
        + [f"-title:({' OR '.join(xt for xt in EXCLUDE_TITLES)})"]
        + [f"-collection:({' OR '.join(xc for xc in EXCLUDE_COLLECTIONS)})"]
        + [f"-subjects:({' OR '.join(xs for xs in EXCLUDE_GENERAL)})"]
        + [f"-creators:({' OR '.join(xs for xs in EXCLUDE_GENERAL)})"]
    )
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

        response = session.get(
            scrape_api_url, headers=headers, params=query_params, timeout=60
        )
        response.raise_for_status()
        data = response.json()
        cursor = data.get("cursor")
        ids += [doc['identifier'] for doc in data.get("items", [])]
        print(
            f"Fetching batch {batch}; adding {len(data.get('items', []))} items -> {len(ids)}"
        )
        batch += 1
    if idfile:
        with open(idfile, 'w') as fout:
            json.dump(ids, fout)
    return ids


def import_ocaids(ocaids: list[str], batch_size=5_000):
    # get the month for yesterday
    date = datetime.date.today() - datetime.timedelta(days=1)
    batch_name = f"new-scans-{date.year:04}{date.month:02}"
    batch = importer.Batch.find(batch_name) or importer.Batch.new(batch_name)

    for items in batched(ocaids, batch_size):
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
