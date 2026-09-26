#!/usr/bin/env python3
"""Utility to move files from local disk to zip files and update the paths in the db"""

import fcntl
import glob
import hashlib
import os
import re
import sys
import time
import zipfile
import zlib
from contextlib import contextmanager, nullcontext
from typing import ClassVar

import internetarchive as ia
import web

from infogami.infobase import utils
from openlibrary.coverstore import config, db
from openlibrary.coverstore.coverlib import (
    find_image_path,  # noqa: F401 side effects may be needed
)
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

ITEM_SIZE = 1_000_000
BATCH_SIZE = 10_000
BATCH_SIZES = ("", "s", "m", "l")
# code.py redirects uploaded covers to archive.org zips only at or above this id;
# below it, older layouts apply, so this module never archives those covers.
MIN_ARCHIVABLE_ID = 8_000_000


def log(*args):
    msg = " ".join(args)
    print(msg)


@contextmanager
def archival_lock():
    """Held by archive(), process_pending and finalize whenever they write, so
    finalize never runs while archive() is appending to a zip it is verifying.
    A second run fails fast.
    """
    path = os.path.join(config.data_root, "items", ".archive.lock")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Read-only: flock needs no write access, so a lock file left by another user still works.
    fd = os.open(path, os.O_RDONLY | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(f"Another archival run holds {path}; wait for it to finish (check `ps`)") from None
        yield
    finally:
        os.close(fd)


class Uploader:
    @staticmethod
    def _get_s3():
        s3_keys = config.get("ia_s3_covers")
        return s3_keys.get("s3_key"), s3_keys.get("s3_secret")

    @classmethod
    def upload(cls, itemname, filepaths):
        md = {
            "title": "Open Library Cover Archive",
            "mediatype": "data",
            "collection": ["ol_data", "ol_exports"],
        }
        access_key, secret_key = cls._get_s3()
        return ia.get_item(itemname).upload(
            filepaths,
            metadata=md,
            retries=10,
            verbose=True,
            access_key=access_key,
            secret_key=secret_key,
        )

    @staticmethod
    def remote_md5(item: str, filename: str) -> str | None:
        """md5 of `filename` in archive.org item `item` (e.g. `s_covers_0008`),
        or None if the item has no file of that exact name.
        """
        for f in ia.get_item(item).files:
            if f["name"] == filename:
                return f.get("md5", "")
        return None

    @classmethod
    def is_uploaded(cls, item: str, filename: str) -> bool:
        """Whether the item has a file of this exact name. Says nothing about
        its contents: #9836 lost covers by trusting this before deleting.
        """
        return cls.remote_md5(item, filename) is not None


class Batch:
    @staticmethod
    def get_relpath(item_id, batch_id, ext="", size=""):
        """e.g. s_covers_0008/s_covers_0008_82.zip or covers_0008/covers_0008_82.zip"""
        ext = f".{ext}" if ext else ""
        prefix = f"{size.lower()}_" if size else ""
        folder = f"{prefix}covers_{item_id}"
        filename = f"{prefix}covers_{item_id}_{batch_id}{ext}"
        return os.path.join(folder, filename)

    @classmethod
    def get_abspath(cls, item_id, batch_id, ext="", size=""):
        """e.g. /1/var/lib/openlibrary/coverstore/items/covers_0008/covers_0008_87.zip"""
        filename = cls.get_relpath(item_id, batch_id, ext=ext, size=size)
        return os.path.join(config.data_root, "items", filename)

    @staticmethod
    def zip_path_to_item_and_batch_id(zpath):
        zfilename = zpath.split(os.path.sep)[-1]
        if match := re.match(r"(?:[lsm]_)?covers_(\d+)_(\d+)\.zip", zfilename):
            return match.group(1), match.group(2)

    @classmethod
    def process_pending(cls, upload=False, finalize=False, test=True):
        """For each batch zipped on local disk:

        1. Skip any size whose local zip is not complete (see is_zip_complete).
        2. Upload any complete zip that archive.org lacks or holds a different
           copy of. This is also how a partial upload gets replaced.
        3. Finalize the batch only if archive.org holds a byte-identical copy
           of every size. A zip uploaded in this run is therefore finalized
           on a later run, once archive.org reports its md5.

        With test=True nothing is uploaded, written to the db or deleted.

        Assumes s, m, l and full zips are in sync: if covers_0008 has
        covers_0008_01.zip, s_covers_0008 also has s_covers_0008_01.zip.
        """
        # test=True only reads, so it can report while another run holds the lock.
        with nullcontext() if test else archival_lock():
            for batch in cls.get_pending():
                item_id, batch_id = cls.zip_path_to_item_and_batch_id(batch)

                print(f"\n## [Processing batch {item_id}_{batch_id}] ##")
                verified = True
                # A finalized batch's archive.org zips are the only copy of its
                # covers; a later local zip of the batch must never replace them.
                finalized = CoverDB().has_uploaded(cls.batch_start_id(item_id, batch_id))

                for size in BATCH_SIZES:
                    itemname, filename = cls.get_relpath(item_id, batch_id, ext="zip", size=size).split(os.path.sep)
                    zip_complete, errors = cls.is_zip_complete(item_id, batch_id, size=size, verbose=True)
                    print(f"* {filename}: Complete? {zip_complete} {errors or ''}")
                    if not zip_complete:
                        verified = False
                        continue
                    # TODO Uploader.check_item_health(itemname)
                    # to ensure no conflicting tasks/redrows
                    if cls.remote_matches_local(item_id, batch_id, size=size):
                        print(f"* {filename}: identical copy on archive.org")
                        continue
                    verified = False
                    if finalized:
                        print(f"=> Not uploading {filename}: batch already finalized, archive.org holds the only copy")
                    elif upload and not test:
                        print(f"=> Uploading {filename} to {itemname}")
                        Uploader.upload(itemname, cls.get_abspath(item_id, batch_id, ext="zip", size=size))
                    elif upload:
                        print(f"=> Would upload {filename} to {itemname} [test=True]")

                print(f"* Finalize? {finalize and verified}")
                if finalize and verified:
                    cls._finalize(item_id, batch_id, test=test)

    @staticmethod
    def get_pending():
        """These are zips on disk which are presumably incomplete or have not
        yet been uploaded
        """
        zipfiles = []
        # find any zips on disk of any size
        item_dirs = glob.glob(os.path.join(config.data_root, "items", "covers_*"))
        for item_dir in item_dirs:
            zipfiles.extend(glob.glob(os.path.join(item_dir, "*.zip")))

        return sorted(zipfiles)

    @staticmethod
    def is_zip_complete(item_id, batch_id, size="", verbose=False):
        """Whether the local zip holds every cover the batch will ever hold:
        the batch is closed, nothing in it is left to archive, and the zip
        has one file per archived cover.
        """
        cdb = CoverDB()
        errors = []
        filepath = Batch.get_abspath(item_id, batch_id, size=size, ext="zip")
        item_id, batch_id = int(item_id), int(batch_id)
        start_id = (item_id * ITEM_SIZE) + (batch_id * BATCH_SIZE)

        if not cdb.is_batch_closed(start_id):
            errors.append({"error": "batch_open", "max_id": cdb.get_max_id()})
        if unarchived := len(cdb.get_batch_unarchived(start_id)):
            errors.append({"error": "archival_incomplete", "remaining": unarchived})
        if not os.path.exists(filepath):
            errors.append({"error": "nozip"})
        else:
            # Counts finalized rows too, so a later zip holding only stragglers never passes.
            expected_num_files = len(cdb.get_batch_archived(start_id=start_id))
            try:
                num_files = ZipManager.count_files_in_zip(filepath)
            except zipfile.BadZipFile:
                num_files = None
                errors.append({"error": "zip_corrupt"})
            if num_files is not None and num_files != expected_num_files:
                errors.append(
                    {
                        "error": "zip_discrepency",
                        "expected": expected_num_files,
                        "actual": num_files,
                    }
                )
        success = not errors
        return (success, errors) if verbose else success

    @classmethod
    def remote_matches_local(cls, item_id, batch_id, size="") -> bool:
        """Whether archive.org holds a byte-identical copy of the local zip."""
        itemname, filename = cls.get_relpath(item_id, batch_id, ext="zip", size=size).split(os.path.sep)
        local = cls.get_abspath(item_id, batch_id, ext="zip", size=size)
        return os.path.exists(local) and Uploader.remote_md5(itemname, filename) == md5sum(local)

    @classmethod
    def is_verified(cls, item_id, batch_id) -> bool:
        """For every size: the local zip is complete and archive.org holds an
        identical copy. This is the only state in which finalize deletes.
        """
        return all(cls.is_zip_complete(item_id, batch_id, size=size) and cls.remote_matches_local(item_id, batch_id, size=size) for size in BATCH_SIZES)

    @staticmethod
    def batch_start_id(item_id, batch_id) -> int:
        return (ITEM_SIZE * int(item_id)) + (BATCH_SIZE * int(batch_id))

    @classmethod
    def finalize(cls, item_id, batch_id, test=True) -> bool:
        """Point a batch's archived covers at its archive.org zips, then delete
        their local files and the local zips.

        Checks for itself, rather than trusting the caller, that the batch is
        verified, that every zip's data passes its checksums, and that every
        local file it will delete is byte-for-byte the zip entry (size and CRC).
        Otherwise it changes nothing. Returns whether it finalized.
        """
        with nullcontext() if test else archival_lock():
            return cls._finalize(item_id, batch_id, test=test)

    @classmethod
    def _finalize(cls, item_id, batch_id, test=True) -> bool:
        """finalize(), for callers already holding archival_lock()."""
        start_id = cls.batch_start_id(item_id, batch_id)
        if start_id < MIN_ARCHIVABLE_ID:
            print(f"=> Refusing to finalize {item_id}_{batch_id}: below {MIN_ARCHIVABLE_ID}")
            return False
        if not cls.is_verified(item_id, batch_id):
            print(f"=> Refusing to finalize {item_id}_{batch_id}: archive.org copy not verified")
            return False

        cdb = CoverDB()
        covers = [Cover(**c) for c in cdb.get_batch_archived(start_id=start_id)]
        zips = {size: cls.get_abspath(item_id, batch_id, ext="zip", size=size) for size in BATCH_SIZES}
        entries: dict[str, dict[str, tuple[int, int]]] = {}
        for size, path in zips.items():
            if (zip_entries := ZipManager.read_entries(path)) is None:
                print(f"=> Refusing to finalize {item_id}_{batch_id}: {os.path.basename(path)} fails its checksums")
                return False
            entries[size] = zip_entries
        if bad := sorted({c.id for c in covers for size in BATCH_SIZES if not matches_zip_entry(entries[size], c.files[Cover.FILE_KEYS[size]])}):
            print(f"=> Refusing to finalize {item_id}_{batch_id}: covers missing from or differing from zips: {bad}")
            return False
        # The entries above must describe what archive.org holds: re-check after reading them.
        if not all(cls.remote_matches_local(item_id, batch_id, size=size) for size in BATCH_SIZES):
            print(f"=> Refusing to finalize {item_id}_{batch_id}: a local zip changed during finalize")
            return False

        to_finalize = [c for c in covers if c.uploaded is False]
        print(f"=> Finalizing {len(to_finalize)} covers in {item_id}_{batch_id} [test={test}]")
        if test:
            return False
        # One cover at a time, repointing before deleting: if this stops midway every
        # cover still resolves, and at most one cover's local files are left behind.
        # A cover whose row did not update keeps its files, and the batch keeps its zips.
        not_repointed = []
        for cover in to_finalize:
            if cdb.update_completed_batch(start_id, ids=[cover.id]) == 1:
                cover.delete_files()
            else:
                not_repointed.append(cover.id)
        if not_repointed:
            print(f"=> Keeping {item_id}_{batch_id}'s zips: rows not repointed: {not_repointed}")
            return False
        for size in reversed(BATCH_SIZES):  # full size last: get_pending() finds batches by it
            print(f"=> Deleting {zips[size]}")
            os.remove(zips[size])
        return True


class CoverDB:
    TABLE = "cover"
    STATUS_KEYS = ("failed", "archived", "uploaded")

    def __init__(self):
        self.db = db.getdb()

    @staticmethod
    def _get_batch_end_id(start_id):
        """Calculates the end of the batch based on the start_id and the
        batch_size
        """
        return start_id - (start_id % BATCH_SIZE) + BATCH_SIZE

    def get_max_id(self) -> int:
        return self.db.query(f"SELECT max(id) AS max_id FROM {self.TABLE}")[0].max_id or 0

    def is_batch_closed(self, start_id) -> bool:
        """A batch is closed once a cover exists past its end. Until then new
        covers can still land in it, so any zip of it is partial (#9836).
        """
        return self.get_max_id() >= self._get_batch_end_id(start_id)

    def has_uploaded(self, start_id) -> bool:
        """Whether any cover in the batch already points at archive.org."""
        end_id = self._get_batch_end_id(start_id)
        where = "id>=$start_id AND id<$end_id AND uploaded=true"
        return bool(self.db.select(self.TABLE, what="id", where=where, vars={"start_id": start_id, "end_id": end_id}, limit=1).list())

    def get_first_unarchived_id(self, min_id) -> int | None:
        rows = self.db.select(
            self.TABLE,
            what="id",
            where="failed=false AND archived=false AND id>=$min_id",
            vars={"min_id": min_id},
            order="id asc",
            limit=1,
        ).list()
        return rows[0].id if rows else None

    def get_covers(self, limit=None, start_id=None, end_id=None, min_id=None, **kwargs):
        """Utility for fetching covers from the database

        start_id: explicitly define a starting id. This is significant
        because an offset would define a number of rows in the db to
        skip but this value may not equate to the desired
        start_id. When start_id used, a end_id is calculated for the
        end of the current batch. When a start_id is used, limit is ignored.

        limit: if no start_id is present, specifies num rows to return.

        min_id: only covers with at least this id.

        kwargs: additional specifiable cover table query arguments
        like those found in STATUS_KEYS
        """
        wheres = [f"{key}=${key}" for key in kwargs if key in self.STATUS_KEYS and kwargs.get(key) is not None]
        if min_id:
            wheres.append("id>=$min_id")
            kwargs["min_id"] = min_id
        if start_id:
            wheres.append("id>=$start_id AND id<$end_id")
            kwargs["start_id"] = start_id
            kwargs["end_id"] = end_id or self._get_batch_end_id(start_id)
            limit = None

        return self.db.select(
            self.TABLE,
            where=" AND ".join(wheres) if wheres else None,
            order="id asc",
            vars=kwargs,
            limit=limit,
        )

    def get_unarchived_covers(self, limit, min_id=0, **kwargs):
        return self.get_covers(limit=limit, min_id=min_id, failed=False, archived=False, **kwargs)

    def _get_current_batch_start_id(self, **kwargs):
        c = self.get_covers(limit=1, **kwargs)[0]
        return c.id - (c.id % BATCH_SIZE)

    def _get_batch(self, start_id=None, **kwargs):
        start_id = start_id or self._get_current_batch_start_id(**kwargs)
        return self.get_covers(start_id=start_id, **kwargs)

    def get_batch_unarchived(self, start_id=None, end_id=None):
        return self._get_batch(
            start_id=start_id,
            failed=False,
            archived=False,
            end_id=end_id,
        )

    def get_batch_archived(self, start_id=None, **kwargs):
        return self._get_batch(start_id=start_id, archived=True, failed=False, **kwargs)

    def get_batch_failures(self, start_id=None):
        return self._get_batch(start_id=start_id, failed=True)

    def update(self, cid, **kwargs):
        return self.db.update(
            self.TABLE,
            where="id=$cid",
            vars={"cid": cid},
            **kwargs,
        )

    def update_completed_batch(self, start_id, ids):
        """Point exactly `ids` (covers of this batch) at the batch's zips."""
        if not ids:
            return 0
        end_id = start_id + BATCH_SIZE
        item_id, batch_id = Cover.id_to_item_and_batch_id(start_id)
        return self.db.update(
            self.TABLE,
            where="id IN $ids AND id>=$start_id AND id<$end_id AND archived=true AND failed=false AND uploaded=false",
            vars={"ids": ids, "start_id": start_id, "end_id": end_id},
            uploaded=True,
            filename=Batch.get_relpath(item_id, batch_id, ext="zip"),
            filename_s=Batch.get_relpath(item_id, batch_id, ext="zip", size="s"),
            filename_m=Batch.get_relpath(item_id, batch_id, ext="zip", size="m"),
            filename_l=Batch.get_relpath(item_id, batch_id, ext="zip", size="l"),
        )


class Cover(web.Storage):
    # BATCH_SIZES entry -> key in self.files
    FILE_KEYS: ClassVar[dict[str, str]] = {"": "filename", "s": "filename_s", "m": "filename_m", "l": "filename_l"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.files = self.get_files()

    @classmethod
    def get_cover_url(cls, cover_id, size="", ext="zip", protocol="https"):
        pcid = "%010d" % int(cover_id)
        img_filename = f"{pcid}{'-' + size.upper() if size else ''}.jpg"
        item_id, batch_id = cls.id_to_item_and_batch_id(cover_id)
        relpath = Batch.get_relpath(item_id, batch_id, size=size, ext=ext)
        path = os.path.join(relpath, img_filename)
        return f"{protocol}://archive.org/download/{path}"

    @property
    def timestamp(self):
        t = utils.parse_datetime(self.created) if isinstance(self.created, str) else self.created
        return time.mktime(t.timetuple())

    def has_valid_files(self):
        return all(f.path and os.path.exists(f.path) for f in self.files.values())

    def get_files(self):
        files = {
            "filename": web.storage(name="%010d.jpg" % self.id, filename=self.filename),
            "filename_s": web.storage(name="%010d-S.jpg" % self.id, filename=self.filename_s),
            "filename_m": web.storage(name="%010d-M.jpg" % self.id, filename=self.filename_m),
            "filename_l": web.storage(name="%010d-L.jpg" % self.id, filename=self.filename_l),
        }
        for file_type, f in files.items():
            files[file_type].path = f.filename and os.path.join(config.data_root, "localdisk", f.filename)
        return files

    def delete_files(self):
        for f in self.files.values():
            if f.path and os.path.exists(f.path):
                print("removing", f.path)
                os.remove(f.path)

    @staticmethod
    def id_to_item_and_batch_id(cover_id):
        """Converts a number like 987_654_321 to a 4-digit, 0-padded item_id
        representing the value of the millions place and a 2-digit,
        0-padded batch_id representing the ten-thousandth place, e.g.

        Usage:
        >>> Cover.id_to_item_and_batch_id(987_654_321)
        ('0987', '65')
        """
        millions = cover_id // ITEM_SIZE
        item_id = f"{millions:04}"
        rem = cover_id - (ITEM_SIZE * millions)
        ten_thousands = rem // BATCH_SIZE
        batch_id = f"{ten_thousands:02}"
        return item_id, batch_id


def archive(limit=None, start_id=None, end_id=None):
    """Add covers from local disk to their batch's zips and mark them archived.

    Never touches the open batch, the one holding the newest cover: covers
    are still landing in it, so a zip of it would be partial (#9836). Never
    touches covers below MIN_ARCHIVABLE_ID either.
    """
    cdb = CoverDB()
    max_id = cdb.get_max_id()
    open_batch_start = max_id - (max_id % BATCH_SIZE)

    if start_id is not None and start_id < MIN_ARCHIVABLE_ID:
        print(f"Not archiving from {start_id}: covers below {MIN_ARCHIVABLE_ID} are not archived by this module")
        return
    if not limit and start_id is None:
        first = cdb.get_first_unarchived_id(min_id=MIN_ARCHIVABLE_ID)
        if first is None:
            print("Nothing to archive")
            return
        start_id = first - (first % BATCH_SIZE)

    with archival_lock(), ZipManager() as file_manager:
        if limit:
            covers = cdb.get_unarchived_covers(limit=limit, min_id=MIN_ARCHIVABLE_ID)
        else:
            covers = cdb.get_batch_unarchived(start_id=start_id, end_id=end_id)

        for cover in covers:
            cover = Cover(**cover)
            if cover.id >= open_batch_start:
                print(f"Stopping at {cover.id:010}: its batch is still open (newest cover is {max_id:010})")
                break
            print("archiving", cover)
            print(cover.files.values())

            if not cover.has_valid_files():
                print("Missing image file for %010d" % cover.id, file=web.debug)
                cdb.update(cover.id, failed=True)
                continue

            for d in cover.files.values():
                file_manager.add_file(d.name, filepath=d.path, mtime=cover.timestamp)
            cdb.update(cover.id, archived=True)


def audit(item_id, batch_ids=(0, 100), sizes=BATCH_SIZES) -> None:
    """Check which cover batches have been uploaded to archive.org.

    Checks the archive.org items pertaining to this `item_id` of up to
    1 million images (4-digit e.g. 0008) for each specified size and
    verify that all the batches (within specified range) and their
    .indic (of 10k images, 2-digit e.g. 81) have been successfully
    uploaded.

    {size}_covers_{item_id}_{batch_id}:
    :param item_id: 4 digit, batches of 1M, 0000 to 9999M
    :param batch_ids: (min, max) batch_id range or max_batch_id; 2 digit, batch of 10k from [00, 99]

    """
    scope = range(*(batch_ids if isinstance(batch_ids, tuple) else (0, batch_ids)))
    for size in sizes:
        files = (Batch.get_relpath(f"{item_id:04}", f"{i:02}", ext="zip", size=size) for i in scope)
        missing_files = []
        sys.stdout.write(f"\n{size or 'full'}: ")
        for f in files:
            item, filename = f.split(os.path.sep, 1)
            print(filename)
            if Uploader.is_uploaded(item, filename):
                sys.stdout.write(".")
            else:
                sys.stdout.write("X")
                missing_files.append(filename)
            sys.stdout.flush()
        sys.stdout.write("\n")
        sys.stdout.flush()
        if missing_files:
            print(f"ia upload {item} {' '.join([f'{item}/{mf}*' for mf in missing_files])} --retries 10")


class ZipManager:
    def __init__(self):
        self.zipfiles = {}
        for size in BATCH_SIZES:
            self.zipfiles[size.upper()] = (None, None)

    @staticmethod
    def names_in_zip(filepath) -> set[str]:
        with zipfile.ZipFile(filepath, "r") as zip_ref:
            return {name for name in zip_ref.namelist() if name.endswith(".jpg")}

    @classmethod
    def count_files_in_zip(cls, filepath) -> int:
        return len(cls.names_in_zip(filepath))

    @staticmethod
    def read_entries(filepath) -> dict[str, tuple[int, int]] | None:
        """name -> (size, CRC-32) for each .jpg in the zip, or None if any
        member's data does not match its recorded CRC.
        """
        with zipfile.ZipFile(filepath, "r") as zip_ref:
            if zip_ref.testzip() is not None:
                return None
            return {i.filename: (i.file_size, i.CRC) for i in zip_ref.infolist() if i.filename.endswith(".jpg")}

    def get_zipfile(self, name):
        cid = web.numify(name)
        zipname = f"covers_{cid[:4]}_{cid[4:6]}.zip"

        # for {cid}-[SML].jpg
        if "-" in name:
            size = name[len(cid + "-") :][0].lower()
            zipname = size + "_" + zipname
        else:
            size = ""

        _zipname, _zipfile = self.zipfiles[size.upper()]
        if _zipname != zipname:
            _zipname and _zipfile.close()
            _zipfile = self.open_zipfile(zipname)
            self.zipfiles[size.upper()] = zipname, _zipfile
            log("writing", zipname)

        return _zipfile

    def open_zipfile(self, name):
        path = os.path.join(config.data_root, "items", name[: -len("_XX.zip")], name)
        dir = os.path.dirname(path)
        if not os.path.exists(dir):
            os.makedirs(dir)
        # Appending to a damaged zip (e.g. after a killed run) silently starts a new one
        # after the damage, hiding covers already marked archived.
        if os.path.exists(path) and not zipfile.is_zipfile(path):
            raise RuntimeError(f"{path} is not a readable zip; it needs repair before archiving continues")

        return zipfile.ZipFile(path, "a")

    def add_file(self, name, filepath, **args):
        zipper = self.get_zipfile(name)

        if name not in zipper.namelist():
            # Set compression to ZIP_STORED to avoid compression
            zipper.write(filepath, arcname=name, compress_type=zipfile.ZIP_STORED)

        return os.path.basename(zipper.filename)

    def close(self):
        for name, _zipfile in self.zipfiles.values():
            if name:
                _zipfile.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    @classmethod
    def contains(cls, zip_file_path, filename):
        with zipfile.ZipFile(zip_file_path, "r") as zip_file:
            return filename in zip_file.namelist()

    @classmethod
    def get_last_file_in_zip(cls, zip_file_path):
        with zipfile.ZipFile(zip_file_path, "r") as zip_file:
            file_list = zip_file.namelist()
            if file_list:
                return max(file_list)


def md5sum(path) -> str:
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "md5").hexdigest()


def crc32(path) -> int:
    crc = 0
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            crc = zlib.crc32(chunk, crc)
    return crc


def matches_zip_entry(entries: dict[str, tuple[int, int]], f) -> bool:
    """Whether cover file `f` is in the zip and, if it is still on local disk,
    is byte-for-byte the zip's entry.
    """
    if f.name not in entries:
        return False
    if not (f.path and os.path.exists(f.path)):
        return True
    size, crc = entries[f.name]
    return os.path.getsize(f.path) == size and crc32(f.path) == crc


def main(openlibrary_yml: str, coverstore_yml: str, dry_run: bool = False):
    """Archive closed batches, upload complete zips, finalize verified batches.
    With --dry-run, only report: nothing is zipped, uploaded, written or deleted.
    """
    from openlibrary.coverstore.server import load_config

    load_config(openlibrary_yml)
    load_config(coverstore_yml)
    if not dry_run:
        archive()
    Batch.process_pending(upload=True, finalize=True, test=dry_run)


if __name__ == "__main__":
    FnToCLI(main).run()
