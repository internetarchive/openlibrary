import web

import openlibrary.core.lists.model as list_model
from openlibrary.mocks.mock_infobase import MockSite


class TestList:
    def test_owner(self):
        list_model.register_models()
        self._test_list_owner("/people/anand")
        self._test_list_owner("/people/anand-test")
        self._test_list_owner("/people/anand_test")

    def _test_list_owner(self, user_key):
        site = MockSite()
        list_key = user_key + "/lists/OL1L"

        self.save_doc(site, "/type/user", user_key)
        self.save_doc(site, "/type/list", list_key)

        list = site.get(list_key)
        assert list is not None
        assert isinstance(list, list_model.List)

        assert list.get_owner() is not None
        assert list.get_owner().key == user_key

    def save_doc(self, site, type, key, **fields):
        d = {"key": key, "type": {"key": type}}
        d.update(fields)
        site.save(d)


class MockWork:
    def __init__(self, key, position):
        self.key = key
        self._position = position

    def find_series_edge(self, series_key):
        return {"position": self._position}


class MockSeriesSite:
    def __init__(self, works):
        self._works = works

    def things(self, query):
        return [work.key for work in self._works]

    def get_many(self, keys):
        return self._works


class TestSeries:
    def test_series_sorting(self, monkeypatch):
        works = [
            MockWork("/works/OL5W", "2"),
            MockWork("/works/OL1W", "22-23"),
            MockWork("/works/OL2W", "1"),
            MockWork("/works/OL3W", "3"),
            MockWork("/works/OL4W", "24-25"),
            MockWork("/works/OL8W", "Non-numeric"),
            MockWork("/works/OL7W", "4-5"),
            MockWork("/works/OL6W", "1-3"),
            MockWork("/works/OL9W", "1-9"),
            MockWork("/works/OL10W", None),
            MockWork("/works/OL11W", "3"),
        ]

        mock_site = MockSeriesSite(works)
        monkeypatch.setattr(web, "ctx", web.storage(site=mock_site))

        series = list_model.Series(mock_site, "/series/OL1L")
        seeds = series.get_seeds()

        result_keys = [seed.key for seed in seeds]
        expected_keys = [
            "/works/OL2W",  # 1
            "/works/OL5W",  # 2
            "/works/OL11W",  # 3 (tie-break by work key)
            "/works/OL3W",  # 3
            "/works/OL10W",  # None -> non-numeric bucket
            "/works/OL8W",  # Non-numeric
            "/works/OL7W",  # 4-5   (range size 1, lower 4)
            "/works/OL1W",  # 22-23 (range size 1, lower 22)
            "/works/OL4W",  # 24-25 (range size 1, lower 24)
            "/works/OL6W",  # 1-3   (range size 2, lower 1)
            "/works/OL9W",  # 1-9   (range size 8, lower 1)
        ]

        assert result_keys == expected_keys


class TestWorkSortKey:
    def test_numeric_position(self):
        class DummyWork:
            def __init__(self, key):
                self.key = key

        work = DummyWork("/works/OL1W")

        key = list_model.get_work_sort_key((work, {"position": "2"}))
        assert key == ("A: Numeric", 1, 2.0, "/works/OL1W")

    def test_range_position(self):
        class DummyWork:
            def __init__(self, key):
                self.key = key

        work = DummyWork("/works/OL1W")

        key = list_model.get_work_sort_key((work, {"position": "1-3"}))
        assert key == ("C: Range", 2, 1.0, "/works/OL1W")

    def test_non_numeric_position(self):
        class DummyWork:
            def __init__(self, key):
                self.key = key

        work = DummyWork("/works/OL1W")

        key = list_model.get_work_sort_key((work, {"position": "abc"}))
        assert key == ("B: Non-numeric", 0, 0.0, "/works/OL1W")

    def test_none_position(self):
        class DummyWork:
            def __init__(self, key):
                self.key = key

        work = DummyWork("/works/OL1W")

        key = list_model.get_work_sort_key((work, {"position": None}))
        assert key == ("B: Non-numeric", 0, 0.0, "/works/OL1W")
