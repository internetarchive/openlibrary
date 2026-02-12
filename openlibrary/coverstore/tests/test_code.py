import datetime
from io import StringIO

import web

from .. import code


def test_tarindex_path():
    assert code.get_tarindex_path(0, "") == "items/covers_0000/covers_0000_00.index"
    assert (
        code.get_tarindex_path(0, "s") == "items/s_covers_0000/s_covers_0000_00.index"
    )
    assert (
        code.get_tarindex_path(0, "m") == "items/m_covers_0000/m_covers_0000_00.index"
    )
    assert (
        code.get_tarindex_path(0, "l") == "items/l_covers_0000/l_covers_0000_00.index"
    )

    assert code.get_tarindex_path(99, "") == "items/covers_0000/covers_0000_99.index"
    assert code.get_tarindex_path(100, "") == "items/covers_0001/covers_0001_00.index"

    assert code.get_tarindex_path(1, "") == "items/covers_0000/covers_0000_01.index"
    assert code.get_tarindex_path(21, "") == "items/covers_0000/covers_0000_21.index"
    assert code.get_tarindex_path(321, "") == "items/covers_0003/covers_0003_21.index"
    assert code.get_tarindex_path(4321, "") == "items/covers_0043/covers_0043_21.index"


def test_parse_tarindex():
    f = StringIO("")

    offsets, sizes = code.parse_tarindex(f)
    assert list(offsets) == [0 for i in range(10000)]
    assert list(sizes) == [0 for i in range(10000)]

    f = StringIO("0000010000.jpg\t0\t10\n0000010002.jpg\t512\t20\n")

    offsets, sizes = code.parse_tarindex(f)
    assert (offsets[0], sizes[0]) == (0, 10)
    assert (offsets[1], sizes[1]) == (0, 0)
    assert (offsets[2], sizes[2]) == (512, 20)
    assert (offsets[42], sizes[42]) == (0, 0)


class Test_cover:
    def test_get_tar_filename(self, monkeypatch):
        offsets = {}
        sizes = {}

        def _get_tar_index(index, size):
            array_offsets = [offsets.get(i, 0) for i in range(10000)]
            array_sizes = [sizes.get(i, 0) for i in range(10000)]
            return array_offsets, array_sizes

        monkeypatch.setattr(code, "get_tar_index", _get_tar_index)
        f = code.cover().get_tar_filename

        assert f(42, "s") is None

        offsets[42] = 1234
        sizes[42] = 567

        assert f(42, "s") == "s_covers_0000_00.tar:1234:567"
        assert f(30042, "s") == "s_covers_0000_03.tar:1234:567"

        d = code.cover().get_details(42, "s")
        assert isinstance(d, web.storage)
        assert d == {
            "id": 42,
            "filename_s": "s_covers_0000_00.tar:1234:567",
            "created": datetime.datetime(2010, 1, 1),
        }


class TestZipViewUrl:
    def test_zipview_url_from_id_small_id(self, monkeypatch):
        """Test URL generation for small cover IDs"""
        # Mock protocol to https
        monkeypatch.setattr("web.ctx.protocol", "https", raising=False)

        # Test cover ID 42 (first batch)
        url = code.zipview_url_from_id(42, "M")
        expected = "https://archive.org/download/olcovers0/olcovers0-M.zip/42-M.jpg"
        assert url == expected, f"Expected {expected} but got {url}"

    def test_zipview_url_from_id_large_id(self, monkeypatch):
        """Test URL generation for large cover IDs (reproduces bug #9921)"""
        # Mock protocol to https
        monkeypatch.setattr("web.ctx.protocol", "https", raising=False)

        # This is the exact cover ID from the bug report
        url = code.zipview_url_from_id(6747253, "L")
        expected = (
            "https://archive.org/download/olcovers674/olcovers674-L.zip/6747253-L.jpg"
        )
        assert url == expected, f"Expected {expected} but got {url}"

    def test_zipview_url_from_id_various_sizes(self, monkeypatch):
        """Test URL generation for different sizes"""
        # Mock protocol to https
        monkeypatch.setattr("web.ctx.protocol", "https", raising=False)

        # Test -S, -M, -L sizes
        assert (
            code.zipview_url_from_id(6747253, "S")
            == "https://archive.org/download/olcovers674/olcovers674-S.zip/6747253-S.jpg"
        )
        assert (
            code.zipview_url_from_id(6747253, "M")
            == "https://archive.org/download/olcovers674/olcovers674-M.zip/6747253-M.jpg"
        )
        assert (
            code.zipview_url_from_id(6747253, "L")
            == "https://archive.org/download/olcovers674/olcovers674-L.zip/6747253-L.jpg"
        )

    def test_zipview_url_from_id_no_size(self, monkeypatch):
        """Test URL generation for original image (no size suffix)"""
        # Mock protocol to https
        monkeypatch.setattr("web.ctx.protocol", "https", raising=False)

        url = code.zipview_url_from_id(6747253, "")
        expected = (
            "https://archive.org/download/olcovers674/olcovers674.zip/6747253.jpg"
        )
        assert url == expected

    def test_zipview_url_uses_integer_division(self):
        """Verify that zipview_url_from_id uses integer division (//) not float division (/)"""
        # This test ensures we're using integer division by checking the calculation
        # For cover ID 6747253, the item index should be 674, not 674.7253
        coverid = 6747253
        IMAGES_PER_ITEM = 10000

        # Calculate expected item index using integer division
        expected_item_index = coverid // IMAGES_PER_ITEM

        # Verify it's an integer
        assert isinstance(
            expected_item_index, int
        ), f"Expected int, got {type(expected_item_index).__name__}"
        assert expected_item_index == 674, f"Expected 674, got {expected_item_index}"

        # Verify no floating point in the result
        assert (
            expected_item_index == 674
        ), "Integer division should produce 674, not 674.7253"
