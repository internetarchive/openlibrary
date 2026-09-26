"""Cover archival must never leave a cover without a copy (#9836).

These tests run the archival recipe (archive() then process_pending) against a
real Postgres, loaded from coverstore/schema.sql, with covers inserted by
db.new(). archive.org is faked: like the real one, it keeps each upload's bytes
as they were when uploaded.

They need a Postgres to run: set OL_TEST_POSTGRES to a libpq-style string,
e.g. "host=localhost port=5432 user=postgres password=postgres dbname=postgres".
CI sets it (.github/workflows/python_tests.yml); without it they are skipped.
"""

import hashlib
import io
import os
import re
import struct
import uuid
import zipfile
from pathlib import Path

import pytest
import web

from openlibrary.coverstore import archive, config, db

BATCH = 14_620_000  # covers_0014_62, the batch #9836 lost covers from
NEXT_BATCH = BATCH + archive.BATCH_SIZE
SUFFIXES = {"": "", "s": "-S", "m": "-M", "l": "-L"}

pytestmark = pytest.mark.skipif(not os.environ.get("OL_TEST_POSTGRES"), reason="needs OL_TEST_POSTGRES")


class FakeArchiveOrg:
    def __init__(self):
        self.files: dict[tuple[str, str], bytes] = {}

    def upload(self, item, path):
        self.files[item, os.path.basename(path)] = Path(path).read_bytes()

    def remote_md5(self, item, filename):
        data = self.files.get((item, filename))
        return None if data is None else hashlib.md5(data).hexdigest()

    def is_uploaded(self, item, filename):
        return (item, filename) in self.files

    def members(self, item, filename) -> set[str]:
        data = self.files.get((item, filename))
        return set(zipfile.ZipFile(io.BytesIO(data)).namelist()) if data else set()

    def truncate(self, item, filename, keep: int):
        """Replace an uploaded zip with one holding only its first `keep` covers."""
        out = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(self.files[item, filename])) as src, zipfile.ZipFile(out, "w") as dst:
            for name in sorted(src.namelist())[:keep]:
                dst.writestr(name, src.read(name))
        self.files[item, filename] = out.getvalue()


class Store:
    def __init__(self, root: Path, sqlite, remote: FakeArchiveOrg):
        self.root, self.db, self.remote = root, sqlite, remote

    def add_covers(self, *ids):
        for cid in ids:
            row = {}
            for size, suffix in SUFFIXES.items():
                rel = f"2024/05/07/{cid}{suffix}.jpg"
                path = self.root / "localdisk" / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(f"cover {cid}{suffix}".encode())
                row[f"filename_{size}" if size else "filename"] = rel
            self.db.query("SELECT setval('cover_id_seq', $n, false)", vars={"n": cid})
            new_id = db.new("b", f"OL{cid}M", author=None, ip="127.0.0.1", source_url=None, width=1, height=1, **row)
            assert new_id == cid

    def _zip(self, cid, size):
        item_id, batch_id = archive.Cover.id_to_item_and_batch_id(cid)
        return archive.Batch.get_relpath(item_id, batch_id, ext="zip", size=size).split(os.path.sep)

    def on_archive_org(self, cid) -> bool:
        return all(f"{cid:010}{suffix}.jpg" in self.remote.members(*self._zip(cid, size)) for size, suffix in SUFFIXES.items())

    def on_local_disk(self, cid) -> bool:
        return all((self.root / "localdisk" / f"2024/05/07/{cid}{suffix}.jpg").exists() for suffix in SUFFIXES.values())

    def lost(self, ids) -> list[int]:
        """Covers with no complete copy anywhere."""
        return [cid for cid in ids if not self.on_local_disk(cid) and not self.on_archive_org(cid)]

    def uploaded(self, ids) -> list[int]:
        rows = self.db.select("cover", where="id >= $lo AND id <= $hi AND uploaded", vars={"lo": min(ids), "hi": max(ids)})
        return sorted(r.id for r in rows)

    def snapshot(self):
        files = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*") if p.is_file())
        return files, [dict(r) for r in self.db.select("cover", order="id")], dict(self.remote.files)


@pytest.fixture
def store(tmp_path, monkeypatch):
    (tmp_path / "localdisk").mkdir()
    monkeypatch.setattr(config, "data_root", str(tmp_path), raising=False)

    params = dict(part.split("=", 1) for part in os.environ["OL_TEST_POSTGRES"].split())
    connect = {"dbn": "postgres", "db": params["dbname"], "user": params["user"], "pw": params.get("password", "")}
    connect |= {k: params[k] for k in ("host", "port") if k in params}
    schema = f"archive_test_{uuid.uuid4().hex[:12]}"
    admin = web.database(**connect)
    admin.query(f"CREATE SCHEMA {schema}")
    pg = web.database(**connect, options=f"-c search_path={schema}")
    pg.query((Path(archive.__file__).parent / "schema.sql").read_text())
    # db.new() sets only archived=False, yet every archival query also filters on
    # failed=false and uploaded=false. Archival has worked in production, so there
    # these columns must default to false; schema.sql does not say so.
    pg.query("ALTER TABLE cover ALTER failed SET DEFAULT false, ALTER uploaded SET DEFAULT false")
    pg.insert("category", name="b")
    monkeypatch.setattr(db, "_db", pg)
    monkeypatch.setattr(db, "_categories", None)

    remote = FakeArchiveOrg()
    monkeypatch.setattr(archive.Uploader, "upload", remote.upload)
    monkeypatch.setattr(archive.Uploader, "is_uploaded", remote.is_uploaded)
    monkeypatch.setattr(archive.Uploader, "remote_md5", remote.remote_md5, raising=False)
    yield Store(tmp_path, pg, remote)
    admin.query(f"DROP SCHEMA {schema} CASCADE")


def run_recipe():
    """What main() and the #8278 recipe run."""
    archive.archive()
    archive.Batch.process_pending(upload=True, finalize=True, test=False)


def test_recipe_keeps_covers_added_after_their_batch_was_first_archived(store):
    """The #9836 sequence: batch 62 was archived and uploaded while still open,
    then took more covers, and a later run deleted them."""
    early, late = list(range(BATCH, BATCH + 3)), list(range(BATCH + 3, BATCH + 6))
    store.add_covers(*early)
    run_recipe()
    assert store.lost(early) == []

    store.add_covers(*late, NEXT_BATCH)  # more covers land in batch 62, then batch 63 opens
    for _ in range(3):
        run_recipe()
        assert store.lost(early + late) == []

    assert all(store.on_archive_org(cid) for cid in early + late)
    assert store.uploaded(early + late) == early + late


def test_open_batch_is_not_zipped_or_uploaded(store):
    store.add_covers(BATCH, BATCH + 1)
    run_recipe()
    assert store.remote.files == {}
    assert list(store.root.rglob("*.zip")) == []
    assert store.db.select("cover", where="archived").list() == []


def test_partial_copy_on_archive_org_is_replaced_not_trusted(store):
    """archive.org holds a partial zip of a closed batch whose covers are still local."""
    ids = list(range(BATCH, BATCH + 4))
    store.add_covers(*ids, NEXT_BATCH)
    run_recipe()  # archives and uploads the whole batch
    for size in SUFFIXES:
        store.remote.truncate(*store._zip(BATCH, size), keep=2)

    archive.Batch.process_pending(upload=False, finalize=True, test=False)
    assert store.lost(ids) == []
    assert store.uploaded(ids) == []

    run_recipe()  # re-uploads the complete zips
    run_recipe()  # finalizes once archive.org matches
    assert store.lost(ids) == []
    assert all(store.on_archive_org(cid) for cid in ids)
    assert store.uploaded(ids) == ids


def test_finalize_refuses_by_itself_when_archive_org_differs(store):
    ids = list(range(BATCH, BATCH + 2))
    store.add_covers(*ids, NEXT_BATCH)
    run_recipe()
    store.remote.truncate(*store._zip(BATCH, "l"), keep=1)

    assert archive.Batch.finalize("0014", "62", test=False) is False
    assert all(store.on_local_disk(cid) for cid in ids)
    assert store.uploaded(ids) == []


def test_leftover_zip_of_open_batch_is_not_uploaded(store):
    """A zip of a still-open batch, as the old code made and could have left on disk."""
    ids = [BATCH, BATCH + 1]
    store.add_covers(*ids)
    zip_covers(store, ids)

    archive.Batch.process_pending(upload=True, finalize=True, test=False)
    assert store.remote.files == {}
    assert all(store.on_local_disk(cid) for cid in ids)


def zip_covers(store, ids):
    """Add covers to their batch's local zips and mark them archived, bypassing archive()'s
    guards, as the old code or a concurrent run would."""
    zips = archive.ZipManager()
    for cid in ids:
        row = store.db.select("cover", where="id=$id", vars={"id": cid})[0]
        for f in archive.Cover(**row).files.values():
            zips.add_file(f.name, filepath=f.path)
    zips.close()
    store.db.update("cover", where="id IN $ids", vars={"ids": list(ids)}, archived=True)


def append_straggler(store, cid):
    """What a concurrent archive() does: add a cover to the batch's local zips, then mark it archived."""
    store.add_covers(cid)
    zip_covers(store, [cid])


def test_cover_archived_during_finalize_is_not_deleted(store, monkeypatch):
    ids = [BATCH, BATCH + 1]
    store.add_covers(*ids, NEXT_BATCH)
    run_recipe()  # uploads
    verified = archive.Batch.is_verified.__func__

    def verified_then_straggler(cls, item_id, batch_id):
        result = verified(cls, item_id, batch_id)
        append_straggler(store, BATCH + 2)
        return result

    monkeypatch.setattr(archive.Batch, "is_verified", classmethod(verified_then_straggler))
    assert archive.Batch.finalize("0014", "62", test=False) is False
    assert store.on_local_disk(BATCH + 2)
    assert store.uploaded(ids + [BATCH + 2]) == []


def test_local_file_differing_from_its_zip_entry_is_not_deleted(store):
    ids = [BATCH, BATCH + 1]
    store.add_covers(*ids, NEXT_BATCH)
    run_recipe()  # uploads
    changed = store.root / "localdisk" / f"2024/05/07/{BATCH}-L.jpg"
    changed.write_bytes(b"not what the zip holds")

    run_recipe()
    assert changed.read_bytes() == b"not what the zip holds"
    assert store.uploaded(ids) == []


def test_zip_whose_data_fails_its_checksum_is_not_finalized(store):
    """Corruption inside a member's data, with its header intact, uploads as-is; finalize must catch it."""
    ids = [BATCH, BATCH + 1]
    store.add_covers(*ids, NEXT_BATCH)
    archive.archive()
    path = archive.Batch.get_abspath("0014", "62", ext="zip", size="l")
    with zipfile.ZipFile(path) as z:
        offset = z.getinfo(f"{BATCH:010}-L.jpg").header_offset
    with open(path, "r+b") as f:
        f.seek(offset + 26)
        name_len, extra_len = struct.unpack("<HH", f.read(4))
        f.seek(offset + 30 + name_len + extra_len)
        byte = f.read(1)
        f.seek(-1, os.SEEK_CUR)
        f.write(bytes([byte[0] ^ 0xFF]))

    run_recipe()  # uploads the corrupt zip, as it matches the db count
    run_recipe()
    assert all(store.on_local_disk(cid) for cid in ids)
    assert store.uploaded(ids) == []


def test_straggler_in_finalized_batch_never_replaces_archive_org_zip(store):
    ids = [BATCH, BATCH + 1]
    store.add_covers(*ids, NEXT_BATCH)
    run_recipe()
    run_recipe()  # finalized
    remote = dict(store.remote.files)

    store.add_covers(BATCH + 2)  # a row that lands in the batch after it was finalized
    run_recipe()
    run_recipe()
    assert store.remote.files == remote
    assert store.lost(ids + [BATCH + 2]) == []


def test_covers_below_min_archivable_id_are_left_alone(store):
    old = [7_320_000, 7_320_001]
    store.add_covers(*old, BATCH, BATCH + 1, NEXT_BATCH)
    archive.archive(start_id=7_320_000)
    archive.archive(limit=10)
    assert store.db.select("cover", where="archived AND id < $min", vars={"min": archive.MIN_ARCHIVABLE_ID}).list() == []
    assert archive.Batch.finalize("0007", "32", test=False) is False

    run_recipe()
    run_recipe()
    assert store.db.select("cover", where="archived AND id < $min", vars={"min": archive.MIN_ARCHIVABLE_ID}).list() == []
    assert all(store.on_local_disk(cid) for cid in old)
    assert store.uploaded(old) == []
    assert store.uploaded([BATCH, BATCH + 1]) == [BATCH, BATCH + 1]


def test_finalize_refuses_below_min_archivable_id(store):
    """A verified zip of old covers, as the old code could have made: code.py would not redirect them."""
    old = [7_320_000, 7_320_001]
    store.add_covers(*old, NEXT_BATCH)
    zip_covers(store, old)
    archive.Batch.process_pending(upload=True, finalize=False, test=False)
    assert archive.Batch.finalize("0007", "32", test=False) is False
    assert all(store.on_local_disk(cid) for cid in old)
    assert store.uploaded(old) == []


def test_second_archival_run_fails_fast(store):
    store.add_covers(BATCH, NEXT_BATCH)
    with archive.archival_lock():
        with pytest.raises(RuntimeError, match="Another archival run"):
            archive.archive()
        with pytest.raises(RuntimeError, match="Another archival run"):
            archive.Batch.process_pending(upload=True, finalize=True, test=False)
        with pytest.raises(RuntimeError, match="Another archival run"):
            archive.Batch.finalize("0014", "62", test=False)
        archive.Batch.process_pending()  # looking is still allowed
    assert store.remote.files == {}


def test_row_with_null_uploaded_keeps_its_files(store):
    ids = [BATCH, BATCH + 1]
    store.add_covers(*ids, NEXT_BATCH)
    run_recipe()  # uploads
    store.db.update("cover", where="id=$id", vars={"id": BATCH + 1}, uploaded=None)

    run_recipe()
    assert store.on_local_disk(BATCH + 1)
    assert store.lost(ids) == []


def test_archive_refuses_to_append_to_a_damaged_zip(store):
    """A zip left unreadable by a killed run: appending would start a new zip after the damage."""
    store.add_covers(BATCH, BATCH + 1, NEXT_BATCH)
    damaged = Path(archive.Batch.get_abspath("0014", "62", ext="zip"))
    damaged.parent.mkdir(parents=True)
    damaged.write_bytes(b"PK\x03\x04 truncated")

    with pytest.raises(RuntimeError, match="not a readable zip"):
        archive.archive()
    assert store.db.select("cover", where="archived").list() == []


def test_corrupt_local_zip_does_not_stop_other_batches(store):
    store.add_covers(BATCH, NEXT_BATCH, NEXT_BATCH + archive.BATCH_SIZE)
    archive.archive()  # batch 62
    archive.archive()  # batch 63
    Path(archive.Batch.get_abspath("0014", "62", ext="zip")).write_bytes(b"not a zip")

    archive.Batch.process_pending(upload=True, finalize=True, test=False)
    assert ("covers_0014", "covers_0014_63.zip") in store.remote.files
    assert ("covers_0014", "covers_0014_62.zip") not in store.remote.files
    assert store.on_local_disk(BATCH)


def test_rerun_after_interrupted_finalize_finishes_cleanly(store, monkeypatch):
    ids = [BATCH, BATCH + 1, BATCH + 2]
    store.add_covers(*ids, NEXT_BATCH)
    run_recipe()  # uploads
    delete_files = archive.Cover.delete_files

    def dies_on_second_cover(self):
        if self.id == BATCH + 1:
            raise OSError("interrupted")
        delete_files(self)

    monkeypatch.setattr(archive.Cover, "delete_files", dies_on_second_cover)
    with pytest.raises(OSError, match="interrupted"):
        run_recipe()
    assert store.lost(ids) == []

    monkeypatch.setattr(archive.Cover, "delete_files", delete_files)
    run_recipe()
    assert store.lost(ids) == []
    assert store.uploaded(ids) == ids
    assert list((store.root / "items").rglob("*.zip")) == []
    # Only the cover interrupted between repoint and delete keeps local files (4 at most).
    leftover = {int(re.match(r"\d+", p.name)[0]) for p in (store.root / "localdisk").rglob("*.jpg")}
    assert leftover & set(ids) == {BATCH + 1}


def test_dry_run_changes_nothing(store):
    store.add_covers(BATCH, BATCH + 1, NEXT_BATCH)
    archive.archive()

    before = store.snapshot()
    archive.Batch.process_pending(upload=True, finalize=True, test=True)  # would upload
    assert store.snapshot() == before

    archive.Batch.process_pending(upload=True, finalize=False, test=False)
    before = store.snapshot()
    archive.Batch.process_pending(upload=True, finalize=True, test=True)  # would finalize
    assert store.snapshot() == before
