import datetime
import io
import os

import pytest

from openlibrary.coverstore_fastapi import config, tar_index


@pytest.fixture
def data_root_with_index(monkeypatch, tmp_path):
    """data_root containing one tar index entry for coverid 12345."""
    monkeypatch.setattr(config, "data_root", str(tmp_path))
    # coverid 12345 -> tarindex 1 -> batch 01 inside item covers_0000
    index_file = tmp_path / "items" / "covers_0000" / "covers_0000_01.index"
    index_file.parent.mkdir(parents=True)
    # name(10 chars) + ".jpg", then offset and size
    index_file.write_text("0000012345.jpg\t100\t200\n")
    tar_index.get_index.cache_clear()
    yield tmp_path
    tar_index.get_index.cache_clear()


def test_index_path_layout():
    assert tar_index.index_path(1, "") == os.path.join("items", "covers_0000", "covers_0000_01.index")
    assert tar_index.index_path(8, "s") == os.path.join("items", "s_covers_0000", "s_covers_0000_08.index")


def test_parse_tarindex():
    file = io.StringIO("0000012345.jpg\t100\t200\n\n0000012346.jpg\t300\t400\n")
    offsets, sizes = tar_index.parse(file)
    # coverid % 10000 gives the slot inside the batch
    assert offsets[2345] == 100
    assert sizes[2345] == 200
    assert offsets[2346] == 300
    assert sizes[2346] == 400
    assert offsets[0] == 0


def test_get_filename_found(data_root_with_index):
    assert tar_index.get_filename(12345, "") == "covers_0000_01.tar:100:200"


def test_get_filename_missing_size_returns_none(data_root_with_index):
    # only the unsized index exists in this fixture
    assert tar_index.get_filename(12345, "s") is None


def test_find_cover_builds_partial_details(data_root_with_index):
    d = tar_index.find_cover(12345, "")
    assert d == {
        "id": 12345,
        "filename": "covers_0000_01.tar:100:200",
        "created": datetime.datetime(2010, 1, 1),
    }
    assert tar_index.find_cover(12345, "m") is None


def test_find_cover_out_of_tar_range():
    # ids >= 6M were never archived into local tars
    assert tar_index.find_cover(6_000_001, "") is None
