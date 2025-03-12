api_url = "https://web.archive.org/save"

# Keys available from https://archive.org/account/s3.php
# Load ENV variables, (don't commit)
headers = {
    "Accept": "application/json",
    "Authorization": f"LOW {access_key}:{secret}"
}

def archive_book(url capture_all=True):
    data = {
      "url": url, # <-- our url here
      "if_not_archived_within": "1m",
    }
    if capture_all and not url.lower().endswith(".pdf"):
        # we don't want to waste a capture_all request if it's just 1 doc
        data["capture_all"] = "1"

    return requests.post(api_url, headers=headers, data=data)
