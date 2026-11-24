"""Regression tests for coverlib olid path-traversal hardening (GHSA-grmp-99r6-3957).

``test_save_image_rejects_unsafe_olid`` is written to FAIL against the unfixed
source: without the olid validation added to ``save_image``, an attacker
controlled olid containing path separators / ``..``, an absolute path, ``:`` or
similar flows unchanged into ``make_path_prefix`` and on into the filesystem, so
``save_image`` does not raise (and, with the DB write stubbed out, would create
files outside the covers ``data_root``). With the fix in place it raises
``ValueError`` before any path is constructed. The positive test guards that
legitimate olids still work.
"""

import io

import pytest
from PIL import Image

from openlibrary.coverstore import config, coverlib, db


def _tiny_jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (0, 128, 255)).save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    """Point coverlib at a throwaway data_root and stub the DB write so the
    tests exercise only the path-construction / validation logic."""
    monkeypatch.setattr(config, "data_root", str(tmp_path), raising=False)
    monkeypatch.setattr(
        config,
        "image_sizes",
        {"S": (6, 6), "M": (12, 12), "L": (24, 24)},
        raising=False,
    )
    monkeypatch.setattr(db, "new", lambda **kwargs: 1)
    return tmp_path


UNSAFE_OLIDS = [
    "../../../../../../tmp/EVIL",  # relative traversal
    "..\\..\\EVIL",  # backslash traversal
    "/etc/cron.d/EVIL",  # absolute path
    "a:b:c",  # ':' routes find_image_path down the items branch
    "OL1M/../../EVIL",  # legit-looking prefix then traversal
    "EVIL space",  # whitespace / non-identifier char
    "",  # empty
]


@pytest.mark.parametrize("olid", UNSAFE_OLIDS)
def test_save_image_rejects_unsafe_olid(isolated_store, olid):
    with pytest.raises(ValueError, match="Invalid olid"):
        coverlib.save_image(_tiny_jpeg(), category="b", olid=olid)


@pytest.mark.parametrize("olid", ["OL1M", "OL123M", "OL1234M", "OL1A", "OL1W"])
def test_save_image_accepts_valid_olid(isolated_store, olid):
    d = coverlib.save_image(_tiny_jpeg(), category="b", olid=olid)
    assert d.olid == olid
    assert d.filename.endswith(".jpg")
