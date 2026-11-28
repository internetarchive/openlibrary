#!/usr/bin/env python
"""Imports the ITAN Global Publishing catalog into Open Library.

ITAN supplies their catalog as a JSONL dump, so unlike most providers there is
nothing to scrape: each line is already close to our import schema and only
needs cleaning up and remapping.
"""

import json
import re
import time
from pathlib import Path
from typing import Any

from openlibrary.config import load_config
from openlibrary.core.imports import Batch
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

# ITAN packs a marketing blurb, an availability/price note, and an edition
# statement into `notes`, separated by pipes, e.g.
#   "<blurb> | Available on Itan Technologies. Ebook: N6,800. | Edition: 0"
NOTES_SEPARATOR = "|"
EDITION_RE = re.compile(r"^Edition:\s*(.*)$", re.IGNORECASE)
AVAILABILITY_RE = re.compile(r"^Available on\b", re.IGNORECASE)
# ITAN uses "0" as a placeholder for books with no distinct edition statement.
# Other values are meaningful: "1", "2" and "3" appear alongside spelled-out
# forms like "Second" and "Revised Edition".
PLACEHOLDER_EDITIONS = {"0", "00"}
ORDINALS = {
    "1": "First",
    "01": "First",
    "1st": "First",
    "first edition": "First",
    "2": "Second",
    "second edition": "Second",
    "3": "Third",
    "third edition": "Third",
}


def normalize_whitespace(value: str) -> str:
    """Collapses runs of whitespace and strips the result.

    ITAN's data has doubled inner spaces and trailing spaces in author names
    and subjects, e.g. "Obinna Godswill  Chinegwu ".
    """
    return re.sub(r"\s+", " ", value).strip()


def strip_author_role(name: str) -> str:
    """Strips a trailing role annotation, e.g. "Jane Doe (Illustrator)" -> "Jane Doe"."""
    return normalize_whitespace(re.sub(r"\s*\([^)]*\)\s*$", "", name))


def parse_notes(notes: str) -> tuple[str, str | None]:
    """Splits ITAN's `notes` into a description and an edition name.

    Returns the blurb and the edition statement, dropping ITAN's availability
    and pricing segment. The edition is None when absent or a placeholder.
    """
    segments = [normalize_whitespace(segment) for segment in notes.split(NOTES_SEPARATOR)]
    description = segments[0]

    edition_name = None
    for segment in segments[1:]:
        if AVAILABILITY_RE.match(segment):
            # Pricing is specific to ITAN's store and not worth importing.
            continue
        if match := EDITION_RE.match(segment):
            edition = match.group(1).strip()
            if edition.lower() not in PLACEHOLDER_EDITIONS:
                # ITAN writes editions as bare numbers as often as words;
                # normalize so we do not store an edition_name of just "2".
                edition_name = ORDINALS.get(edition.lower(), edition)

    return description, edition_name


def map_data(record: dict[str, Any]) -> dict[str, Any]:
    """Maps a raw ITAN catalog record to an Open Library import object."""
    itan_id = record["identifiers"]["itan_technologies"][0]
    description, edition_name = parse_notes(record.get("notes", ""))

    import_record: dict[str, Any] = {
        "title": normalize_whitespace(record["title"]),
        "source_records": [f"itan_technologies:{itan_id}"],
        "publishers": [normalize_whitespace(publisher) for publisher in record["publishers"]],
        "publish_date": record["publish_date"],
        "authors": [{"name": normalize_whitespace(author["name"])} for author in record["authors"]],
        "languages": record["languages"],
        "identifiers": {"itan_technologies": [itan_id]},
    }

    if subtitle := normalize_whitespace(record.get("subtitle", "")):
        import_record["subtitle"] = subtitle

    subjects = [normalize_whitespace(subject) for subject in record.get("subjects", [])]
    # ITAN repeats subjects with inconsistent spacing; dedupe while keeping order.
    subjects = list(dict.fromkeys(subject for subject in subjects if subject))
    if subjects:
        import_record["subjects"] = subjects
    if contributions := [strip_author_role(name) for name in record.get("contributions", [])]:
        import_record["contributions"] = contributions

    if description:
        import_record["description"] = description

    if edition_name:
        import_record["edition_name"] = edition_name

    # ITAN sends 0 for books whose page count is unknown.
    if number_of_pages := record.get("number_of_pages"):
        import_record["number_of_pages"] = number_of_pages

    # Book pages use a full slug that cannot be derived from the ITAN ID, so we
    # keep the URL ITAN supplies rather than building one from the identifier.
    if url := record.get("url"):
        import_record["links"] = [{"url": url, "title": "Read on ITAN"}]

    # `isbn_13` in ITAN's dump is a placeholder ("0" or "978"), never a real
    # ISBN, so it is deliberately dropped.

    return import_record


def create_batch(records: list[dict[str, Any]]) -> None:
    """Creates the ITAN batch import job.

    Attempts to find an existing ITAN import batch. If nothing is found, a new
    batch is created. All of the given import records are added to the batch
    job as JSON strings.
    """
    now = time.gmtime(time.time())
    batch_name = f"itan-{now.tm_year}{now.tm_mon:02}"
    batch = Batch.find(batch_name) or Batch.new(batch_name)
    batch.add_items([{"ia_id": r["source_records"][0], "data": r} for r in records])


def import_job(
    ol_config: str,
    catalog: str,
    dry_run: bool = False,
    limit: int | None = None,
) -> None:
    """
    :param str ol_config: Path to openlibrary.yml file
    :param str catalog: Path to ITAN's itan_catalog.jsonl dump
    :param bool dry_run: If true, only print out records to import
    :param int limit: If set, only process the first N records (useful for testing)
    """
    load_config(ol_config)

    lines = Path(catalog).read_text(encoding="utf-8").splitlines()
    records = [map_data(json.loads(line)) for line in lines if line.strip()]
    if limit:
        records = records[:limit]

    if not dry_run:
        create_batch(records)
        print(f"{len(records)} entries added to the batch import job.")
    else:
        for record in records:
            print(json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    print("Start: ITAN import job")
    FnToCLI(import_job).run()
    print("End: ITAN import job")
