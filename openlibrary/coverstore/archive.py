"""Utility to move files from local disk to tar files and update the paths in the db.
"""

import web
import os
import sys
import subprocess
import time
import tarfile
import zipfile

from infogami.infobase import utils

from openlibrary.coverstore import config, db
from openlibrary.coverstore.coverlib import find_image_path


def log(*args):
    msg = " ".join(args)
    print(msg)


def get_filepath(item_id, batch_id, ext="", size=""):
    ext = ".{ext}" if ext else ""
    prefix = f"{size.lower()}_" if size else ""
    folder = f"{prefix}covers_{item_id}"
    filename = f"{prefix}covers_{item_id}_{batch_id}{ext}"
    filepath = os.path.join(config.data_root, "items" folder, filename)
    print(filepath)
    return filepath



class CoverDB:
    TABLE = 'cover'
    BATCH_SIZE = 10_000
    ITEM_SIZE = 1_000_000
    STATUS_KEYS = ('failed', 'archived', 'deleted', 'uploaded')

    def __init__(self):
        self.db = db.getdb()

    def is_zip_complete(self, item_id, batch_id, size="", verbose=False):
        errors = []
        filepath = get_filepath(item_id, batch_id, size=size, ext="zip")
        item_id, batch_id = int(item_id), int(batch_id)
        start_id = (item_id * self.ITEM_SIZE) + (batch_id * self.BATCH_SIZE)
        unarchived = len(self.get_batch_unarchived(start_id))

        if unarchived:
            errors.append({"error": "archival_incomplete", "remaining": unarchived})
        if not os.path.exists(filepath):
            errors.append({'error': 'nozip'})
        else:
            expected_num_files = len(self.get_batch_archived(start_id=start_id))
            num_files = ZipManager.count_files_in_zip(filepath)
            if num_files != expected_num_files:
                errors.append({
                    "error": "zip_discrepency",
                    "expected": expected_num_files,
                    "actual": num_files
                })
        success = not len(errors)
        return success, errors if verbose else success

    @classmethod
    def get_batch_end_id(cls, start_id):
        """Calculates the end of the batch based on the start_id and the
        batch_size
        """
        return start_id - (start_id % cls.BATCH_SIZE) + cls.BATCH_SIZE

    def get_covers(self, limit=None, start_id=None, **kwargs):
        """Utility for fetching covers from the database

        start_id: explicitly define a starting id. This is significant
        because an offset would define a number of rows in the db to
        skip but this value may not equate to the desired
        start_id. When start_id used, a end_id is calculated for the
        end of the current batch. When a start_id is used, limit is ignored.

        limit: if no start_id is present, specifies num rows to return.

        kwargs: additional specifiable cover table query arguments
        like those found in STATUS_KEYS
        """
        wheres = [
            f"{key}=${key}"
            for key in kwargs
            if key in self.STATUS_KEYS and kwargs.get(key) is not None
        ]
        if start_id:
            wheres.append("id>=$start_id AND id<$end_id")
            kwargs['start_id'] = start_id
            kwargs['end_id'] = self.get_batch_end_id(start_id)
            limit = None

        return self.db.select(
            self.TABLE,
            where=" AND ".join(wheres) if wheres else None,
            order='id asc',
            vars=kwargs,
            limit=limit,
        )

    def get_unarchived_covers(self, limit, **kwargs):
        return self.get_covers(
            limit=limit, failed=False, archived=False, uploaded=False, **kwargs
        )

    def _get_current_batch_start_id(self, **kwargs):
        c = self.get_covers(limit=1, **kwargs)[0]
        return c.id - (c.id % self.BATCH_SIZE)

    def _get_batch(self, **kwargs):
        start_id = self._get_current_batch_start_id(**kwargs)
        return self.get_covers(start_id=start_id, **kwargs)

    def get_batch_unarchived(self):
        return self._get_batch(failed=False, archived=False, uploaded=False)

    def get_batch_failures(self):
        return self._get_batch(failed=True)

    def get_batch_undeleted(self):
        return self._get_batch(deleted=False)

    def update(self, cid, **kwargs):
        return self.db.update(
            self.TABLE,
            where="id=$cid",
            vars={'cid': cid},
            **kwargs,
        )


def archive(limit=None, start_id=0, archive_format='zip'):
    """Move files from local disk to tar files and update the paths in the db."""

    file_manager = TarManager() if archive_format == 'tar' else ZipManager()
    cdb = CoverDB()

    try:
        covers = (
            cdb.get_unarchived_covers(limit=limit) if limit
            else cdb.get_batch_unarchived(start_id=start_id)
        )

        for cover in covers:
            print('archiving', cover)
            files = get_cover_files(cover)
            print(files.values())

            if any(d.path and os.path.exists(d.path) for d in files.values()):
                print("Missing image file for %010d" % cover.id, file=web.debug)
                cdb.update(cover.id, failed=True)
                continue

            if isinstance(cover.created, str):
                cover.created = utils.parse_datetime(cover.created)
            timestamp = time.mktime(cover.created.timetuple())

            for d in files.values():
                d.newname = file_manager.add_file(
                    d.name, filepath=d.path, mtime=timestamp
                )
            cdb.update(cover.id, archived=True)
    finally:
        file_manager.close()


def get_cover_files(cover):
    files = {
        'filename': web.storage(name="%010d.jpg" % cover.id, filename=cover.filename),
        'filename_s': web.storage(
            name="%010d-S.jpg" % cover.id, filename=cover.filename_s
        ),
        'filename_m': web.storage(
            name="%010d-M.jpg" % cover.id, filename=cover.filename_m
        ),
        'filename_l': web.storage(
            name="%010d-L.jpg" % cover.id, filename=cover.filename_l
        ),
    }
    for file_type, f in files.items():
        files[file_type].path = f.filename and os.path.join(
            config.data_root, "localdisk", f.filename
        )
    return files


def is_uploaded(item: str, filename_pattern: str) -> bool:
    """
    Looks within an archive.org item and determines whether
    either a .zip files exists or whether both a .tar and its .index files exist

    :param item: name of archive.org item to look within
    :param filename_pattern: filename pattern to look for
    """
    zip_command = fr'ia list {item} | grep "{filename_pattern}\.zip" | wc -l'
    zip_result = subprocess.run(command, shell=True, text=True, capture_output=True)
    if int(zip_result.stdout.strip()) == 1:
        return True

    tar_command = fr'ia list {item} | grep "{filename_pattern}\.[tar|index]" | wc -l'
    tar_result = subprocess.run(command, shell=True, text=True, capture_output=True)
    if int(tar_result.stdout.strip()) == 2:
        return True

    return False


def audit(group_id, chunk_ids=(0, 100), sizes=('', 's', 'm', 'l')) -> None:
    """Check which cover batches have been uploaded to archive.org.

    Checks the archive.org items pertaining to this `group` of up to
    1 million images (4-digit e.g. 0008) for each specified size and verify
    that all the chunks (within specified range) and their .indices + .tars (of 10k images, 2-digit
    e.g. 81) have been successfully uploaded.

    {size}_covers_{group}_{chunk}:
    :param group_id: 4 digit, batches of 1M, 0000 to 9999M
    :param chunk_ids: (min, max) chunk_id range or max_chunk_id; 2 digit, batch of 10k from [00, 99]

    """
    scope = range(*(chunk_ids if isinstance(chunk_ids, tuple) else (0, chunk_ids)))
    for size in sizes:
        files = (get_filepath(f"{group_id:04}", f"{i:02}", size=size) for i in scope)
        missing_files = []
        sys.stdout.write(f"\n{size or 'full'}: ")
        for f in files:
            if is_uploaded(item, f):
                sys.stdout.write(".")
            else:
                sys.stdout.write("X")
                missing_files.append(f)
            sys.stdout.flush()
        sys.stdout.write("\n")
        sys.stdout.flush()
        if missing_files:
            print(
                f"ia upload {item} {' '.join([f'{item}/{mf}*' for mf in missing_files])} --retries 10"
            )


class ZipManager:
    def __init__(self):
        self.zipfiles = {}
        for size in ['', 'S', 'M', 'L']:
            self.zipfiles[size] = (None, None)

    @staticmethod
    def count_files_in_zip(filepath):
        command = f'unzip -l {filepath} | grep "jpg" |  wc -l'
        result = subprocess.run(command, shell=True, text=True, capture_output=True)
        return int(result.stdout.strip())

    def get_zipfile(self, name):
        cid = web.numify(name)
        zipname = f"covers_{cid[:4]}_{cid[4:6]}.zip"

        # for {cid}-[SML].jpg
        if '-' in name:
            size = name[len(cid + '-') :][0].lower()
            zipname = size + "_" + zipname
        else:
            size = ""

        _zipname, _zipfile = self.zipfiles[size.upper()]
        if _zipname != zipname:
            _zipname and _zipfile.close()
            _zipfile = self.open_zipfile(zipname)
            self.zipfiles[size.upper()] = zipname, _zipfile
            log('writing', zipname)

        return _zipfile

    def open_zipfile(self, name):
        path = os.path.join(config.data_root, "items", name[: -len("_XX.zip")], name)
        dir = os.path.dirname(path)
        if not os.path.exists(dir):
            os.makedirs(dir)

        return zipfile.ZipFile(path, 'a')

    def add_file(self, name, filepath, **args):
        zipper = self.get_zipfile(name)

        if name not in zipper.namelist():
            with open(filepath, 'rb') as fileobj:
                # Set compression to ZIP_STORED to avoid compression
                zipper.write(filepath, arcname=name, compress_type=zipfile.ZIP_STORED)

        return os.path.basename(zipper.filename)

    def close(self):
        for name, _zipfile in self.zipfiles.values():
            if name:
                _zipfile.close()

    @classmethod
    def contains(cls, zip_file_path, filename):
        with zipfile.ZipFile(zip_file_path, 'r') as zip_file:
            return filename in zip_file.namelist()

    @classmethod
    def get_last_file_in_zip(cls, zip_file_path):
        with zipfile.ZipFile(zip_file_path, 'r') as zip_file:
            file_list = zip_file.namelist()
            if file_list:
                return max(file_list)

    def __init__(self):
        self.tarfiles = {}
        self.tarfiles[''] = (None, None, None)
        self.tarfiles['S'] = (None, None, None)
        self.tarfiles['M'] = (None, None, None)
        self.tarfiles['L'] = (None, None, None)

    def get_tarfile(self, name):
        cid = web.numify(name)
        tarname = f"covers_{id[:4]}_{id[4:6]}.tar"

        # for cid-[SML].jpg
        if '-' in name:
            size = name[len(cid + '-') :][0].lower()
            tarname = size + "_" + tarname
        else:
            size = ""

        _tarname, _tarfile, _indexfile = self.tarfiles[size.upper()]
        if _tarname != tarname:
            _tarname and _tarfile.close()
            _tarfile, _indexfile = self.open_tarfile(tarname)
            self.tarfiles[size.upper()] = tarname, _tarfile, _indexfile
            log('writing', tarname)

        return _tarfile, _indexfile

    def open_tarfile(self, name):
        path = os.path.join(config.data_root, "items", name[: -len("_XX.tar")], name)
        dir = os.path.dirname(path)
        if not os.path.exists(dir):
            os.makedirs(dir)

        indexpath = path.replace('.tar', '.index')
        print(indexpath, os.path.exists(path))
        mode = 'a' if os.path.exists(path) else 'w'
        # Need USTAR since that used to be the default in Py2
        return tarfile.TarFile(path, mode, format=tarfile.USTAR_FORMAT), open(
            indexpath, mode
        )

    def add_file(self, name, filepath, mtime):
        with open(filepath, 'rb') as fileobj:
            tarinfo = tarfile.TarInfo(name)
            tarinfo.mtime = mtime
            tarinfo.size = os.stat(fileobj.name).st_size

            tar, index = self.get_tarfile(name)

            # tar.offset is current size of tar file.
            # Adding 512 bytes for header gives us the
            # starting offset of next file.
            offset = tar.offset + 512

            tar.addfile(tarinfo, fileobj=fileobj)

            index.write(f'{name}\t{offset}\t{tarinfo.size}\n')
            return f"{os.path.basename(tar.name)}:{offset}:{tarinfo.size}"

    def close(self):
        for name, _tarfile, _indexfile in self.tarfiles.values():
            if name:
                _tarfile.close()
                _indexfile.close()


class TarManager:
    def __init__(self):
        self.tarfiles = {}
        self.tarfiles[''] = (None, None, None)
        self.tarfiles['S'] = (None, None, None)
        self.tarfiles['M'] = (None, None, None)
        self.tarfiles['L'] = (None, None, None)

    def get_tarfile(self, name):
        cid = web.numify(name)
        tarname = f"covers_{cid[:4]}_{cid[4:6]}.tar"

        # for {cid}-[SML].jpg
        if '-' in name:
            size = name[len(cid + '-') :][0].lower()
            tarname = size + "_" + tarname
        else:
            size = ""

        _tarname, _tarfile, _indexfile = self.tarfiles[size.upper()]
        if _tarname != tarname:
            _tarname and _tarfile.close()
            _tarfile, _indexfile = self.open_tarfile(tarname)
            self.tarfiles[size.upper()] = tarname, _tarfile, _indexfile
            log('writing', tarname)

        return _tarfile, _indexfile

    def open_tarfile(self, name):
        path = os.path.join(config.data_root, "items", name[: -len("_XX.tar")], name)
        dir = os.path.dirname(path)
        if not os.path.exists(dir):
            os.makedirs(dir)

        indexpath = path.replace('.tar', '.index')
        print(indexpath, os.path.exists(path))
        mode = 'a' if os.path.exists(path) else 'w'
        # Need USTAR since that used to be the default in Py2
        return tarfile.TarFile(path, mode, format=tarfile.USTAR_FORMAT), open(
            indexpath, mode
        )

    def add_file(self, name, filepath, mtime):
        with open(filepath, 'rb') as fileobj:
            tarinfo = tarfile.TarInfo(name)
            tarinfo.mtime = mtime
            tarinfo.size = os.stat(fileobj.name).st_size

            tar, index = self.get_tarfile(name)

            # tar.offset is current size of tar file.
            # Adding 512 bytes for header gives us the
            # starting offset of next file.
            offset = tar.offset + 512

            tar.addfile(tarinfo, fileobj=fileobj)

            index.write(f'{name}\t{offset}\t{tarinfo.size}\n')
            return f"{os.path.basename(tar.name)}:{offset}:{tarinfo.size}"

    def close(self):
        for name, _tarfile, _indexfile in self.tarfiles.values():
            if name:
                _tarfile.close()
                _indexfile.close()
