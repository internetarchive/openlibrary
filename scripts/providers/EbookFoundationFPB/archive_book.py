import os
from contextlib import redirect_stdout

import requests

from openlibrary.config import load_config


def format_archive_book_request(url, capture_all: bool = True, capture_outlinks: bool = True, capture_screenshot: bool = True) -> dict[str, str]:
    data = {
        "url": url,  # <-- our url here
        "if_not_archived_within": "1m",
    }

    if capture_all and not url.lower().endswith(".pdf"):
        # we don't want to waste a capture_all request if it's just 1 doc
        data["capture_all"] = "1"

    if capture_outlinks:
        data["capture_outlinks"] = "1"

    if capture_screenshot:
        data["capture_screenshot"] = "1"

    return data

def post_data(headers: dict[str, str], data: dict) -> dict:
    api_url = "https://web.archive.org/save"
    return requests.post(api_url, headers=headers, data=data)


if __name__ == "__main__":
    ol_config = os.getenv("OL_CONFIG")

    if ol_config:
        with open(os.devnull, 'w') as devnull, redirect_stdout(devnull):
            load_config(ol_config)

        # header = {}
        # data = format_archive_book_request("")
        # response = post_data(header, data)
        