"""
To run:

PYTHONPATH=. python ./scripts/providers/EbookFoundation/import_fpb.py /olsystem/etc/openlibrary.yml
"""

import contextlib
import datetime
import json
import logging
import re
import time

import requests
from bs4 import BeautifulSoup

from openlibrary.config import load_config
from openlibrary.core.imports import Batch
from openlibrary.plugins.upstream.utils import get_marc21_language
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

# GitHub raw content URL for the JSON file on EbookFoundation
FPB_URL = "https://raw.githubusercontent.com/EbookFoundation/free-programming-books-search/main/fpb.json"
logger = logging.getLogger("openlibrary.importer.fpb")


def fix_text_format(text: str) -> str:
    """
    Cleans and normalizes a string by fixing encoding issues and standardizing line breaks.

    - Attempts to re-encode the text from 'latin1' to 'utf-8' to fix common mojibake issues
      (e.g., incorrectly displayed accented characters).
    - Silently skips re-encoding if it raises encoding/decoding errors.
    - Replaces Windows-style line breaks (\r\n) with Unix-style (\n).
    - Collapses multiple consecutive newlines into a single newline.

    Args:
        text (str): The input string potentially containing encoding issues and inconsistent line breaks.

    Returns:
        str: The cleaned and normalized text.
    """

    with contextlib.suppress(UnicodeEncodeError, UnicodeDecodeError):
        text = text.encode('latin1').decode('utf-8', errors='ignore')

    text = text.replace("\r\n", "\n")
    text = re.sub(r'\n+', '\n', text)
    return text


def fetch_data_from_ebookfoundation(max_retries: int = 10, delay: int = 5) -> dict:
    """
    Fetches JSON data from the Ebook Foundation URL with retry logic.

    Retries the request up to `max_retries` times with a delay of `delay` seconds
    between attempts if a RequestException occurs.

    Args:
        max_retries (int): Maximum number of retry attempts (default is 10).
        delay (int): Number of seconds to wait between retries (default is 5).

    Returns:
        dict: Parsed JSON data if the request is successful; otherwise, {}.
    """

    attempt = 0

    while True:
        try:
            response = requests.get(FPB_URL, timeout=10)
            response.raise_for_status()  # Raise an error if request fails
            logger.info("Successfully fetched data from Ebook Foundation.")
            return response.json()  # Successfully fetched JSON
        except requests.exceptions.RequestException as e:
            attempt += 1
            logger.warning(
                f"Attempt {attempt}: Failed to fetch JSON ({e}). Retrying in {delay} seconds..."
            )
            time.sleep(delay)  # Wait before retrying

            if attempt >= max_retries:
                logger.error("Max retries reached. Exiting without data.")
                return {}  # Return None if max retries are exceeded


def detect_inaccessible_books(url: str) -> tuple[bool, str]:
    """
    Checks whether a given URL is accessible and doesn't contain typical error content.

    Args:
        url (str): The URL to check.

    Returns:
        tuple: (bool, str) — True and message if accessible, otherwise False and reason.
    """

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.google.com/",
    }

    try:
        response_head = requests.head(url, allow_redirects=True, timeout=10)
        response_code = response_head.status_code

        if response_code == 200:
            return True, f"Page accessible code {response_code}"

        response = requests.get(url, allow_redirects=True, timeout=10)
        response_text = response.text

        if not response_text:
            response = requests.get(
                url, headers=headers, allow_redirects=True, timeout=10
            )
            response_text = response.text

        # Check content
        soup = BeautifulSoup(response_text, 'html.parser')
        title_text = soup.title.string if soup.title else "No title found"
        title = title_text.lower().strip()

        # Check if title indicates page not found
        if "not found" in title or "404" in title or "error" in title:
            return (
                False,
                f"Page might be available but contains error content. Title: {title}",
            )

        # You could also check for specific error text in the body
        body_text = soup.get_text().lower().strip()[:1000]
        error_phrases = ["page not found", "does not exist", "could not be found"]

        for phrase in error_phrases:
            if phrase in body_text:
                return False, f"Page content contains error phrase: '{phrase}'"

        return True, f"Page accessible code {response_code}"

    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to access {url}: {e}")
        return False, f"Error accessing page: {e}"


def scrape_metadata(url: str) -> dict:
    """
    Scrapes Open Graph and other metadata (title, author, publisher, publish date, description, cover image)
    from a given URL.

    Args:
        url (str): The URL of the webpage to scrape.

    Returns:
        dict: A dictionary containing metadata fields with extracted values, or empty defaults on failure.
    """

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.google.com/",
    }

    try:
        # Send HTTP request to fetch the webpage content
        response = requests.get(url, allow_redirects=True, timeout=10)
        response_text = response.text

        if not response_text:
            response = requests.get(
                url, headers=headers, allow_redirects=True, timeout=10
            )
            response_text = response.text

        # Parse HTML content using BeautifulSoup
        soup = BeautifulSoup(response_text, 'html.parser')

        # Extract Open Graph metadata
        title = (
            soup.find("meta", property="og:title")
            or soup.find("meta", property="twitter:title")
            or soup.find("meta", attrs={"name": "title"})
        )
        author = soup.find_all("meta", attrs={"name": "author"})
        publisher = soup.find_all("meta", attrs={"name": "publisher"})
        publish_date = soup.find("meta", attrs={"name": "publisher_date"})
        description = (
            soup.find("meta", property="og:description")
            or soup.find("meta", property="twitter:description")
            or soup.find("meta", attrs={"name": "description"})
        )
        cover_image = soup.find("meta", property="og:image") or soup.find(
            "meta", property="twitter:image"
        )

        authors, publishers = [], []
        for a in author:
            if a.get("content"):
                authors.append({"name": a["content"].strip()})

        for p in publisher:
            if p.get("content"):
                publishers.append(p["content"].strip())

        # Get the content attributes
        metadata = {
            "title": title.get("content", "").strip() if (title) else "",
            "authors": authors,
            "publishers": publishers,
            "publish_date": (
                publish_date.get("content", "").strip() if (publish_date) else ""
            ),
            "description": (
                description.get("content", "").strip() if (description) else ""
            ),
            "cover": cover_image.get("content", "") if (cover_image) else "",
        }

        return metadata
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to scrape metadata from {url}: {e}")
        return {
            "title": "",
            "authors": [],
            "publishers": [],
            "publish_date": "",
            "description": "",
            "cover": "",
        }


def flatten_books(data: dict) -> list[dict]:
    """
    Recursively flattens a nested EbookFoundation dataset structure into a list of book entries.

    Each entry in the returned list is a dictionary representing a single book, including:
    - title, authors, and subjects (inferred from section hierarchy)
    - source record and URL
    - access format (pdf, epub, or web)
    - placeholder values for missing metadata like publisher or publish date
    - language code if available and valid

    Args:
        data (dict): The nested JSON-like structure containing book sections organized by language and topics.

    Returns:
        list: A list of dictionaries where each dictionary is a flat representation of a book entry.
    """

    flat_list = []

    def traverse(sections, topics, language_code):
        for section in sections:
            new_topics = topics + [fix_text_format(section["section"])]

            # Process entries at the current section level
            for book in section.get("entries", []):
                if "url" not in book:
                    continue

                authors = []
                raw_authors = book["author"].split(",") if ("author" in book) else []

                for author in raw_authors:
                    if not author:
                        continue

                    authors.append({"name": fix_text_format(author.strip())})

                notes = "".join(book.get("notes", []))
                format = ""

                if "pdf" in notes.lower():
                    format = "pdf"
                elif "epub" in notes.lower():
                    format = "epub"
                else:
                    format = "web"

                entry = {
                    "title": fix_text_format(book.get("title", "????")),
                    "authors": authors,
                    "source_records": ["EbookFoundation:%s" % book["url"]],
                    "publishers": ["????"],
                    "publish_date": "20xx",
                    "subjects": new_topics,
                    "providers": [
                        {
                            "url": book["url"],
                            "access": "read",
                            "format": format,
                            "provider_name": "EbookFoundation",
                        }
                    ],
                }

                if language_code and language_code != "????":
                    entry["languages"] = [language_code]

                flat_list.append(entry)

            if "subsections" not in section or not section["subsections"]:
                continue

            # Process subsections recursively
            traverse(section["subsections"], new_topics, language_code)

    # Start traversing from the root
    for child in data.get("children", []):
        if child["type"] == "books":
            for language_section in child.get("children", []):
                if "sections" not in language_section:
                    continue

                language_name = (
                    language_section["language"].get("code", "????")
                    if ("language" in language_section)
                    else "????"
                )

                language_code = get_marc21_language(language_name)

                traverse(language_section["sections"], [], language_code)

    logger.info(f"Flattening complete. Total books found: {len(flat_list)}")
    return flat_list


def process_books() -> list[dict]:
    """
    Fetches raw book data from the EbookFoundation, flattens the data into book entries,
    checks the accessibility of each book, and scrapes additional metadata to enrich the book information.

    The function performs the following tasks:
    1. Fetches raw data from the EbookFoundation API.
    2. Flattens the data into a list of book entries.
    3. For each book, checks the accessibility of the associated URL.
    4. If the book is accessible, scrapes metadata (title, authors, publishers, etc.).
    5. Updates the book entry with the scraped metadata, if available.
    6. If any field is missing, the function tries to fill it with placeholder data.
    7. Returns a list of processed books with enriched metadata.

    Returns:
        list: A list of books with metadata including title, authors, publishers,
              publish date, description, and cover image URL.
    """

    logger.info("Fetching raw data from EbookFoundation...")
    raw_data = fetch_data_from_ebookfoundation()

    if not raw_data:
        logger.error("Failed to fetch data. Exiting process.")
        return []

    logger.info("Flattening raw data into book entries...")
    data = flatten_books(raw_data)
    books = []

    logger.info(f"Processing {len(data)} books...")
    for i, book in enumerate(data):
        url = book["providers"][0]["url"]
        logger.debug(f"[{i+1}/{len(data)}] Checking accessibility for URL: {url}")

        result, reason = detect_inaccessible_books(url)

        if not result:
            logger.warning(f"Skipping inaccessible book at {url}. Reason: {reason}")
            continue

        logger.debug(f"Scraping metadata for URL: {url}")
        metadata = scrape_metadata(url)

        if metadata["title"] and not book["title"]:
            book["title"] = fix_text_format(metadata["title"])
            logger.debug(f"Title updated from metadata: {book['title']}")

        if metadata["authors"] and not book["authors"]:
            for author in metadata["authors"]:
                author["name"] = fix_text_format(author["name"])

            book["authors"] = metadata["authors"]
            logger.debug(f"Authors added from metadata: {book['authors']}")

        if metadata["publishers"]:
            for i in range(len(metadata["publishers"])):
                metadata["publishers"][i] = fix_text_format(metadata["publishers"][i])

            book["publishers"] = metadata["publishers"]
            logger.debug(f"Publishers added from metadata: {book['publishers']}")

        if metadata["publish_date"]:
            book["publish_date"] = fix_text_format(metadata["publish_date"])
            logger.debug(f"Publish date added from metadata: {book['publish_date']}")

        if metadata["description"]:
            book["description"] = fix_text_format(metadata["description"])
            logger.debug("Description added from metadata.")

        if metadata["cover"] and "githubassets" not in metadata["cover"]:
            book["cover"] = metadata["cover"]
            logger.debug(f"Cover image URL added: {book['cover']}")

        if not book["authors"]:
            book["authors"].append({"name": "EbookFoundation Unknown"})
            logger.debug("Author unknown, added placeholder.")

        books.append(book)

    logger.info(
        f"Processing complete. {len(books)} accessible books processed successfully."
    )
    return books


def main(ol_config: str, batch_size: int = 1000, dry_run: bool = False) -> None:
    """
    :param ol_config: Path to openlibrary.yml file
    :param batch_size: Number of items to submit per batch
    :param dry_run: If True, do not submit to the batch system
    """
    load_config(ol_config)
    books = process_books()

    if not dry_run:
        load_config(ol_config)
        date = datetime.date.today()
        batch_name = f"fpb_ebookfoundation-{date:%Y%m}"
        batch = Batch.find(batch_name) or Batch.new(batch_name)

    book_items = []
    for line_num, book in enumerate(books):
        book_items.append({'ia_id': book['source_records'][0], 'data': book})

        if dry_run:
            print(json.dumps(book))
        # If we have enough items, submit a batch
        elif not ((line_num + 1) % batch_size):
            batch.add_items(book_items)
            book_items = []  # clear added items

    # Add any remaining book_items to batch
    if not dry_run and book_items:
        batch.add_items(book_items)


if __name__ == "__main__":
    FnToCLI(main).run()
