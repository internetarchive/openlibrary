from getpass import getpass

import requests

# Prompt user for secrets securely
access_key = getpass("Enter your access key: ")
secret = getpass("Enter your secret key: ")

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


# response = archive_book("")
# print(response.json())
