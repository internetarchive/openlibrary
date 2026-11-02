from getpass import getpass

import requests

from scripts.providers.EbookFoundationFPB.import_fpb import (
    detect_inaccessible_books,
    fetch_data_from_ebookfoundation,
    flatten_books,
)


def process_urls(include_error_links: bool = False) -> list[str]:
    """
    Fetches book URLs from the Ebook Foundation dataset.

    If include_error_links is False, filters out inaccessible links using
    detect_inaccessible_books. Otherwise, returns all URLs.

    Args:
        include_error_links (bool): Whether to include URLs that fail accessibility checks.

    Returns:
        list[str]: A list of book provider URLs.
    """

    raw_data = fetch_data_from_ebookfoundation()
    books = flatten_books(raw_data)
    all_urls = []

    for book in books:
        all_urls.append(book["providers"][0]["url"])

    if not include_error_links:
        working_urls = []

        for url in all_urls:
            result, _ = detect_inaccessible_books(url)

            if result:
                working_urls.append(url)

        return working_urls

    return all_urls


def format_archive_book_request(
    url,
    capture_all: bool = True,
    capture_outlinks: bool = True,
    capture_screenshot: bool = True,
) -> dict[str, str]:
    """
    Formats a request payload for the Internet Archive Save Page Now API.

    Args:
        url (str): The URL to archive.
        capture_all (bool): Whether to request a full page capture (including all resources).
        capture_outlinks (bool): Whether to capture linked pages.
        capture_screenshot (bool): Whether to request a screenshot of the page.

    Returns:
        dict[str, str]: A dictionary formatted for submission to the archive API.
    """

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
    """
    Sends a POST request to the Internet Archive Save Page Now API.

    Args:
        headers (dict[str, str]): HTTP headers to include in the request.
        data (dict): The form data to be submitted.

    Returns:
        dict: A dictionary containing the parsed JSON response, or an error message
        if the response is not valid JSON.
    """

    api_url = "https://web.archive.org/save"
    response = requests.post(api_url, headers=headers, data=data)

    try:
        return response.json()
    except ValueError:
        return {
            "error": "Response is not valid JSON",
            "status_code": response.status_code,
        }


if __name__ == "__main__":
    # Prompt user for secrets securely
    access_key = getpass("Enter your access key: ")
    secret = getpass("Enter your secret key: ")

    headers = {
        "Accept": "application/json",
        "Authorization": f"LOW {access_key}:{secret}",
    }

    urls = process_urls(True)

    for url in urls:
        data = format_archive_book_request(url)
        response = post_data(headers, data)
