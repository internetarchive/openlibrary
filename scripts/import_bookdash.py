#!/usr/bin/env python
import json
import re
import time
from typing import Any
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

from openlibrary.config import load_config
from openlibrary.core.imports import Batch
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

SITEMAP_URL = "https://bookdash.org/books-sitemap.xml"
SITEMAP_NS = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
ISBN_RE = re.compile(r"ISBN:\s*([\d\-Xx]+)")
REQUEST_TIMEOUT = 30


def get_sitemap_urls() -> list[str]:
    """Fetches and returns all Bookdash book page URLs from their sitemap."""
    response = requests.get(SITEMAP_URL, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    urls = [loc.text for loc in root.findall(".//ns:loc", SITEMAP_NS)]
    # The sitemap includes the /books/ index page itself; only keep individual book pages.
    return [url for url in urls if url and url.rstrip("/") != "https://bookdash.org/books"]


def scrape_book_page(url: str) -> dict[str, Any]:
    """Fetches a single Bookdash book page and extracts its raw metadata."""
    response = requests.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    title_tag = soup.find("h1")
    if not title_tag:
        raise ValueError(f"Missing <h1> title on {url}")
    title = title_tag.get_text(strip=True)

    cover_url = None
    if (picture := soup.find("picture")) and (cover_img := picture.find("img")):
        cover_url = cover_img.get("data-src") or cover_img.get("src")

    description_tag = soup.find("meta", attrs={"property": "og:description"})
    description = description_tag["content"] if description_tag else ""

    languages = [a["href"].removeprefix("/languages/") for a in soup.find_all("a", href=True) if a["href"].startswith("/languages/")]

    subjects = [a.get_text(strip=True) for a in soup.find_all("a", href=True) if a["href"].startswith("/themes/")]

    authors = [a.get_text(strip=True) for a in soup.find_all("a", href=True) if "/team-members/" in a["href"]]

    isbn_match = ISBN_RE.search(soup.get_text())
    isbn = isbn_match.group(1) if isbn_match else None

    return {
        "url": url,
        "title": title,
        "cover_url": cover_url,
        "description": description,
        "languages": languages,
        "subjects": subjects,
        "authors": authors,
        "isbn": isbn,
    }


def strip_author_role(name: str) -> str:
    """Strips a trailing role annotation, e.g. "Jane Doe(Illustrator)" -> "Jane Doe"."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()


def map_data(scraped: dict[str, Any]) -> dict[str, Any]:
    """Maps a scraped Bookdash book dict to an Open Library import object."""
    slug = scraped["url"].rstrip("/").split("/")[-1]

    import_record: dict[str, Any] = {
        "title": scraped["title"],
        "source_records": [f"bookdash:{slug}"],
        "publishers": ["Bookdash"],
        "authors": [{"name": strip_author_role(name)} for name in scraped["authors"]],
        "languages": scraped["languages"],
        "subjects": scraped["subjects"],
        "description": scraped["description"],
    }

    if scraped.get("isbn"):
        import_record["identifiers"] = {"isbn_13": [scraped["isbn"]]}

    if scraped.get("cover_url"):
        import_record["cover"] = scraped["cover_url"]

    return import_record


def create_batch(records: list[dict[str, Any]]) -> None:
    """Creates the Bookdash batch import job.

    Attempts to find an existing Bookdash import batch. If nothing is
    found, a new batch is created. All of the given import records are
    added to the batch job as JSON strings.
    """
    now = time.gmtime(time.time())
    batch_name = f"bookdash-{now.tm_year}{now.tm_mon}"
    batch = Batch.find(batch_name) or Batch.new(batch_name)
    batch.add_items([{"ia_id": r["source_records"][0], "data": r} for r in records])


def import_job(
    ol_config: str,
    dry_run: bool = False,
    limit: int | None = None,
) -> None:
    """
    :param str ol_config: Path to openlibrary.yml file
    :param bool dry_run: If true, only print out records to import
    :param int limit: If set, only process the first N URLs (useful for testing)
    """
    load_config(ol_config)

    urls = get_sitemap_urls()
    if limit:
        urls = urls[:limit]

    records = []
    for url in urls:
        scraped = scrape_book_page(url)
        records.append(map_data(scraped))
        time.sleep(0.5)  # be polite to Bookdash's server

    if not dry_run:
        create_batch(records)
        print(f"{len(records)} entries added to the batch import job.")
    else:
        for record in records:
            print(json.dumps(record))


if __name__ == "__main__":
    print("Start: Bookdash import job")
    FnToCLI(import_job).run()
    print("End: Bookdash import job")
