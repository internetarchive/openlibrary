"""Author photos (category "a") are archived and served like book covers (#13761, for #9836).

Author photos are rows in the same `cover` table as book covers, told apart only by
category_id. Nothing in archive.py or in serving by id reads category_id, so an author
photo is zipped, uploaded and finalized with its batch, and once finalized
/a/id/<id>.jpg redirects into that batch's zip on archive.org. These tests pin that,
with a book cover beside each author photo as the control.

TestServingFinalizedPhotos needs nothing external. TestArchival runs archive() and
process_pending() against a real Postgres loaded from schema.sql, with archive.org
faked; set OL_TEST_POSTGRES to a libpq-style string to run it, e.g.
"host=localhost port=5432 user=postgres password=postgres dbname=postgres".
"""

import datetime
import hashlib
import io
import os
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import web
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openlibrary.coverstore import archive, code, config, db

COVER_ID = 14_700_000  # covers_0014_70: above the 8M redirect floor, not a real batch's contents
SUFFIXES = {"": "", "S": "-S", "M": "-M", "L": "-L"}


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(code.router)
    return TestClient(app)


class TestServingFinalizedPhotos:
    """Serving by id, with db.details stubbed to a finalized row."""

    @pytest.fixture
    def row(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "data_root", str(tmp_path))
        row = web.storage(
            id=COVER_ID,
            filename="2024/05/07/photo.jpg",
            filename_s="2024/05/07/photo-S.jpg",
            filename_m="2024/05/07/photo-M.jpg",
            filename_l="2024/05/07/photo-L.jpg",
            uploaded=True,
            created=datetime.datetime(2024, 5, 7),
        )
        monkeypatch.setattr(code.db, "details", lambda coverid: row if coverid == COVER_ID else None)
        return row

    @pytest.mark.parametrize("category", ["a", "b"])
    @pytest.mark.parametrize(
        ("size", "location"),
        [
            ("", "http://archive.org/download/covers_0014/covers_0014_70.zip/0014700000.jpg"),
            ("S", "http://archive.org/download/s_covers_0014/s_covers_0014_70.zip/0014700000-S.jpg"),
            ("M", "http://archive.org/download/m_covers_0014/m_covers_0014_70.zip/0014700000-M.jpg"),
            ("L", "http://archive.org/download/l_covers_0014/l_covers_0014_70.zip/0014700000-L.jpg"),
        ],
    )
    def test_finalized_photo_redirects_into_its_batch_zip(self, client, row, category, size, location):
        r = client.get(f"/{category}/id/{COVER_ID}{SUFFIXES[size]}.jpg", follow_redirects=False)
        assert (r.status_code, r.headers["location"]) == (302, location)

    @pytest.mark.parametrize("category", ["a", "b"])
    def test_photo_not_yet_uploaded_is_served_from_local_disk(self, client, row, tmp_path, category):
        """The control for the test above: the redirect is decided by `uploaded`, not by category."""
        path = tmp_path / "localdisk" / row.filename_l
        path.parent.mkdir(parents=True)
        path.write_bytes(b"local photo")
        row.uploaded = False

        r = client.get(f"/{category}/id/{COVER_ID}-L.jpg", follow_redirects=False)
        assert (r.status_code, r.content) == (200, b"local photo")


class FakeArchiveOrg:
    """Keeps each upload's bytes as they were when uploaded, like archive.org."""

    def __init__(self):
        self.files: dict[tuple[str, str], bytes] = {}

    def upload(self, item, path):
        self.files[item, os.path.basename(path)] = Path(path).read_bytes()

    def is_uploaded(self, item, filename, verbose=False):
        return (item, filename) in self.files

    def remote_file(self, item, filename):
        data = self.files.get((item, filename))
        return None if data is None else {"md5": hashlib.md5(data).hexdigest(), "size": str(len(data))}

    def remote_md5(self, item, filename):
        f = self.remote_file(item, filename)
        return None if f is None else f["md5"]

    def read_member(self, item, zipname, member) -> bytes | None:
        data = self.files.get((item, zipname))
        if data is None:
            return None
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            return z.read(member) if member in z.namelist() else None


@pytest.mark.skipif(
    not os.environ.get("OL_TEST_POSTGRES"),
    reason="needs OL_TEST_POSTGRES; master's CI has no Postgres service until #13725 adds one",
)
class TestArchival:
    """archive() then process_pending(), as main() runs them, on a batch holding one
    author photo and one book cover."""

    @pytest.fixture
    def pg(self, tmp_path, monkeypatch):
        (tmp_path / "localdisk").mkdir()
        monkeypatch.setattr(config, "data_root", str(tmp_path))

        params = dict(part.split("=", 1) for part in os.environ["OL_TEST_POSTGRES"].split())
        connect = {"dbn": "postgres", "db": params["dbname"], "user": params["user"], "pw": params.get("password", "")}
        connect |= {k: params[k] for k in ("host", "port") if k in params}
        schema = f"author_photos_test_{uuid.uuid4().hex[:12]}"
        admin = web.database(**connect)
        admin.query(f"CREATE SCHEMA {schema}")
        pg = web.database(**connect, options=f"-c search_path={schema}")
        pg.query((Path(archive.__file__).parent / "schema.sql").read_text())
        # db.new() sets only archived=False, and archival filters on failed=false and
        # uploaded=false, which a NULL never matches. That holds for every category, so
        # default them here the way production must, and leave it out of this question.
        pg.query("ALTER TABLE cover ALTER failed SET DEFAULT false, ALTER uploaded SET DEFAULT false")
        pg.insert("category", name="a")
        pg.insert("category", name="b")
        monkeypatch.setattr(db, "_db", pg)
        monkeypatch.setattr(db, "_categories", None)
        yield pg
        admin.query(f"DROP SCHEMA {schema} CASCADE")

    @pytest.fixture
    def remote(self, monkeypatch):
        remote = FakeArchiveOrg()
        monkeypatch.setattr(archive.Uploader, "upload", remote.upload)
        monkeypatch.setattr(archive.Uploader, "is_uploaded", remote.is_uploaded)
        # Not on master's Uploader; #13725's finalize checks archive.org's md5 with them.
        monkeypatch.setattr(archive.Uploader, "remote_file", remote.remote_file, raising=False)
        monkeypatch.setattr(archive.Uploader, "remote_md5", remote.remote_md5, raising=False)
        return remote

    @pytest.fixture
    def covers(self, pg, tmp_path):
        """{category: (cover_id, {size: bytes})}, one author photo and one book cover.

        A newer cover in the next batch closes theirs, as in production. #13725 does not
        archive the batch holding the newest cover; master archives it regardless."""
        covers = {}
        batch = [(COVER_ID, "a", "OL1A"), (COVER_ID + 1, "b", "OL1M"), (COVER_ID + archive.BATCH_SIZE, "b", "OL2M")]
        for cid, category, olid in batch:
            row, originals = {}, {}
            for size, suffix in SUFFIXES.items():
                rel = f"2024/05/07/{cid}{suffix}.jpg"
                path = tmp_path / "localdisk" / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                originals[size] = f"{category} photo {cid}{suffix}".encode()
                path.write_bytes(originals[size])
                row[f"filename_{size.lower()}" if size else "filename"] = rel
            pg.query("SELECT setval('cover_id_seq', $n, false)", vars={"n": cid})
            assert db.new(category, olid, author=None, ip="127.0.0.1", source_url=None, width=1, height=1, **row) == cid
            covers.setdefault(category, (cid, originals))
        return covers

    @staticmethod
    def archive_and_finalize():
        """main()'s two steps, then process_pending() again to finalize what the first
        run uploaded. A second main() would not get that far here: with nothing left to
        archive, master's archive() raises IndexError, whatever the category."""
        archive.archive()
        archive.Batch.process_pending(upload=True, finalize=True, test=False)
        archive.Batch.process_pending(upload=True, finalize=True, test=False)

    @pytest.mark.parametrize("category", ["a", "b"])
    def test_photo_is_finalized_into_its_batch_zip(self, pg, remote, covers, tmp_path, category):
        self.archive_and_finalize()

        cid, _ = covers[category]
        cover = pg.select("cover", where="id=$cid", vars={"cid": cid})[0]
        assert db.get_category_id(category) == cover.category_id
        assert (cover.archived, cover.uploaded, cover.failed) == (True, True, False)
        assert [cover.filename, cover.filename_s, cover.filename_m, cover.filename_l] == [
            "covers_0014/covers_0014_70.zip",
            "s_covers_0014/s_covers_0014_70.zip",
            "m_covers_0014/m_covers_0014_70.zip",
            "l_covers_0014/l_covers_0014_70.zip",
        ]
        assert not list((tmp_path / "localdisk").rglob(f"{cid}*.jpg"))

    @pytest.mark.parametrize("category", ["a", "b"])
    @pytest.mark.parametrize("size", list(SUFFIXES))
    def test_finalized_photo_serves_the_bytes_archive_org_holds(self, pg, remote, covers, client, category, size):
        self.archive_and_finalize()

        cid, originals = covers[category]
        r = client.get(f"/{category}/id/{cid}{SUFFIXES[size]}.jpg", follow_redirects=False)
        assert r.status_code == 302
        url = urlsplit(r.headers["location"])
        assert url.netloc == "archive.org"
        _, _download, item, zipname, member = url.path.split("/")
        assert remote.read_member(item, zipname, member) == originals[size]
