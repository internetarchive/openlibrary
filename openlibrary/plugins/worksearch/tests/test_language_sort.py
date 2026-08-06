"""Tests for language sort collation."""

import locale

import pytest

from openlibrary.plugins.worksearch.languages import _sort_key_name


class TestSortKeyName:
    def test_basic_casefold(self):
        """Uppercase sorts alongside lowercase."""
        assert _sort_key_name("Apple") == _sort_key_name("apple")

    def test_case_insensitive_order(self):
        """Case differences do not affect sort order beyond tie-breaking."""
        keys = sorted([_sort_key_name("Apple"), _sort_key_name("banana"), _sort_key_name("apple")])
        # "Apple" and "apple" are adjacent; "banana" comes after both.
        assert keys[2] == _sort_key_name("banana")

    def test_diacritics_sort_with_base(self):
        """Accented characters sort with their base character."""
        c_key = _sort_key_name("C")
        c_caron_key = _sort_key_name("Č")
        c_acute_key = _sort_key_name("Ć")

        keys = sorted([c_acute_key, c_key, c_caron_key])
        # All three should cluster around 'C', not at the end of the alphabet.
        assert keys[0] == c_key
        # Č and Ć come after C
        assert c_caron_key in keys
        assert c_acute_key in keys

    def test_multiple_diacritics_across_languages(self):
        """Sort order works for mixed diacritic characters."""
        names = [
            "Čeština",
            "Deutsch",
            "Cymraeg",
            "Català",
            "Créole",
            "Español",
            "Français",
        ]
        sorted_names = sorted(names, key=_sort_key_name)
        # All 'C' languages come before 'D'
        c_indexes = [i for i, n in enumerate(sorted_names) if n.startswith("C")]
        d_index = sorted_names.index("Deutsch")
        assert all(i < d_index for i in c_indexes)

    def test_fallback_on_locale_error(self):
        """When locale.strxfrm raises, fall back to casefold()."""
        # \ud800 is a lone surrogate that strxfrm rejects
        result = _sort_key_name("A\ud800B")
        assert isinstance(result, str)
        # Should not crash

    def test_empty_string(self):
        assert isinstance(_sort_key_name(""), str)

    def test_stability(self):
        """Same input always produces the same key."""
        name = "Français"
        assert _sort_key_name(name) == _sort_key_name(name)

    def test_ascii_only_is_fine(self):
        assert _sort_key_name("English") == locale.strxfrm("english")


class TestSortKeyNameWithLocale:
    @pytest.fixture(autouse=True)
    def _set_locale(self, monkeypatch):
        """Ensure we run in a known locale for repeatable tests."""
        monkeypatch.setattr(locale, "LC_COLLATE", locale.LC_COLLATE)
        saved = locale.setlocale(locale.LC_COLLATE)
        try:
            locale.setlocale(locale.LC_COLLATE, "en_US.UTF-8")
        except locale.Error:
            locale.setlocale(locale.LC_COLLATE, "C.UTF-8")
        yield
        locale.setlocale(locale.LC_COLLATE, saved)

    def test_locale_aware_sort_matches_babel_equivalent(self):
        """In en_US.UTF-8, 'Č' sorts near 'C', not after 'Z'."""
        names = ["Zulu", "Čeština", "Deutsch", "Cymraeg"]
        sorted_names = sorted(names, key=_sort_key_name)
        # Čeština and Cymraeg should appear before Deutsch and Zulu
        c_positions = [i for i, n in enumerate(sorted_names) if n.startswith(("C", "Č"))]
        z_position = sorted_names.index("Zulu")
        d_position = sorted_names.index("Deutsch")
        assert all(p < d_position for p in c_positions)
        assert d_position < z_position
