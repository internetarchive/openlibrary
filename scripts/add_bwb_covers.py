#!/usr/bin/env python3
"""
Add Better World Books cover images to corresponding Open Library Editions if needed.

Phase 1: generate_covers_dict()
Read thru all zipfiles in ol-home0:/1/var/tmp/imports/2022/covers to create a dict of
the zip files and their ISBN-13s that have a cover image jpg file associated with them.

Phase 2: edition_needs_a_cover()
Determine which ISBN-13s need a cover image added to their Open Library record.
Possible outcomes could be:
1. ISBN is not in Open Library
2. ISBN is in Open Library and already has a cover image
3. ISBN is in Open Library and needs a cover image added
Each ISBN's dict could be updated with NOT_IN_OPEN_LIBRARY, HAS_COVER, or NEEDS_COVER
and the Edition.olid.
There is a slow way to determine if a cover is needed by using the `olclient` module
and a fast way of doing to determine this by using direct access to web.ctx.site.things

Phase 3: update_cover_for_edition()
For each Edition.olid that NEEDS_COVER in the dict, add the cover image jpg from the
zipfile to its Open Library Edition.

Issues:
1. Phase 1 needs read access to BWB zipfiles in ol-home0:/1/var/tmp/imports/2022/covers
2. slow_edition_needs_a_cover() takes a long time to find each Open Library Edition.
3. fast_edition_needs_a_cover() required direct access to web.ctx.site.things().
4. Could read-many methods of access accelerate the edition_needs_a_cover() process?
"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from os import environ
from pathlib import Path
from time import perf_counter
from collections.abc import Iterator
from zipfile import ZipFile

import web

import _init_path  # noqa: F401  Imported for its side effect of setting PYTHONPATH
import infogami
from infogami import config

import openlibrary
from openlibrary.config import load_config
from openlibrary.utils.dateutil import elapsed_time

load_config('/olsystem/etc/openlibrary.yml')
infogami._setup()

# NOTE: The current year is currently hard coded.
# COVERS_DIR = Path("/1/var/tmp/imports/2022/covers")  # on ol:home0
COVERS_DIR = Path("/imports/2022/covers")  # As mapped by docker-compose.production.yml


@elapsed_time("generate_covers_dict()")
def generate_covers_dict(covers_dir: Path = COVERS_DIR) -> dict:
    """
    Generate a dictionary of all ISBN-13s that have an associated cover .jpg file in
    the zip files in covers_dir.  This process currently takes about 17 sec to generate
    a dict containing 1.3M ISBN-13s.

    {'Apr2022_1_lc_13.zip': [{'9780000528742': []},
                             {'9780006499268': []},
                             {'9780006499305': []},
    """
    from operator import attrgetter

    def get_isbn_13s_from_zipfile(zipfile_path: Path) -> Iterator[dict[str, list]]:
        with ZipFile(zipfile_path) as in_file:
            for cover_file in sorted(in_file.infolist(), key=attrgetter("filename")):
                parts = cover_file.filename.split(".")  # 9780425030134.jpg
                assert parts[-1] == "jpg", cover_file.filename
                yield {parts[0]: []}

    return {
        zipfile_path.name: list(get_isbn_13s_from_zipfile(zipfile_path))
        for zipfile_path in sorted(covers_dir.glob("*.zip"))
    }


'''
def slow_edition_needs_a_cover(isbn_13: str) -> str:
    """
    If the Open Library Edition with this ISBN-13 has no cover then return its olid.
    """
    if ol_edition := openlibrary.Edition.get(isbn=isbn_13):
        if not getattr(ol_edition, "covers", None):
            return ol_edition.olid
    return ""
'''


def fast_edition_needs_a_cover(isbn_13: str) -> str:
    """
    If the Open Library Edition with this ISBN-13 has no cover then return its olid.
    """
    import web

    query = {"type": "/type/edition", "isbn_": isbn_13}
    if keys := web.ctx.site.things(query):
        ol_edition = keys[0]
        if not getattr(ol_edition, "covers", None):
            return ol_edition.olid
    return ""


'''
def update_cover_for_edition(
    edition_olid: str, file_name: str, cover_data: bytes, mime_type: str = "image/jpeg"
) -> bool:
    url = f"https://openlibrary.org/books/{edition_olid}/-/add-cover"
    form_data_body = {
        "file": (file_name, cover_data, mime_type),
        "url": (None, "https://"),
        "upload": (None, "Submit"),
    }
    resp = openlibrary.session.post(url, files=form_data_body)
    return resp.ok and "Saved!" in resp.text
'''


@elapsed_time("main()")
def main(covers_dir: Path = COVERS_DIR):
    edition_needs_a_cover = fast_edition_needs_a_cover
    covers_dict = generate_covers_dict(covers_dir)
    # from pprint import pprint
    # pprint(covers_dict)
    print(f"{len(covers_dict)} zip files with {sys.getsizeof(covers_dict)} bytes.")
    for zipfile_name, isbn_13s in covers_dict.items():
        with ZipFile(covers_dir / zipfile_name) as in_file:
            covers_updated = 0
            for i, isbn_13 in enumerate(isbn_13s):
                if ol_edition := edition_needs_a_cover(isbn_13):
                    cover_file_name = f"{isbn_13}.jpg"
                    print(f">> {i} {zipfile_name}: {cover_file_name}")
                    if cover_data := in_file.read(cover_file_name):
                        """
                        if update_cover_for_edition(
                            ol_edition.olid, cover_file_name, cover_data
                        ):
                        """
                    covers_updated += 1
                    if covers_updated > 5:
                        break
            print(f"{zipfile_name}: {covers_updated} of {i+1} covers updated.")


if __name__ == "__main__":
    main()
