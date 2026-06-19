"""Tests for openlibrary.plugins.worksearch.languages."""

from openlibrary.plugins.worksearch.languages import _name_sort_key


class TestNameSortKey:
    def test_case_insensitive(self):
        assert _name_sort_key("English") == _name_sort_key("english")

    def test_diacritics_sort_with_base_letter(self):
        # "É" should sort the same as "E", not after "Z"
        assert _name_sort_key("Église") == _name_sort_key("eglise")

    def test_diacritic_order(self):
        # "Ébène" should sort before "F", not after "Z"
        names = ["French", "Ébène", "German"]
        sorted_names = sorted(names, key=_name_sort_key)
        assert sorted_names == ["Ébène", "French", "German"]

    def test_mixed_case_order(self):
        # uppercase should not sort before lowercase
        names = ["afrikaans", "English", "Zulu"]
        sorted_names = sorted(names, key=_name_sort_key)
        assert sorted_names == ["afrikaans", "English", "Zulu"]
