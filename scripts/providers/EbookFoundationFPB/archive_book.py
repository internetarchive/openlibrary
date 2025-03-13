import requests
import os
from openlibrary.config import load_config
from contextlib import redirect_stdout

# Define the API URL and headers
api_url = "https://web.archive.org/save"
headers = {"Accept": "application/json", "Authorization": f"LOW {access_key}:{secret}"}


def archive_book(url, capture_all=True, capture_outlinks=True, capture_screenshot=True):
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

    return requests.post(api_url, headers=headers, data=data)

if __name__ == "__main__":
    ol_config = os.getenv("OL_CONFIG")
    
    if ol_config:
        logger.info(f"loading config from {ol_config}")
        # Squelch output from infobase (needed for sentry setup)
        # So it doesn't end up in our data dumps body
        with open(os.devnull, 'w') as devnull, redirect_stdout(devnull):
            load_config(ol_config)

    # response = archive_book("")
    # print(response.json())
