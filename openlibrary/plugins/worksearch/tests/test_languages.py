"""Locale-independent sorting for language names on /languages?sort=name."""

import asyncio

from openlibrary.plugins.worksearch import languages


def test_language_name_sort_key_ignores_case_and_combining_accents():
    names = ["Č", "B", "Ć", "d", "C", "Á", "a"]
    assert sorted(names, key=languages.language_name_sort_key) == ["a", "Á", "B", "C", "Ć", "Č", "d"]
    assert languages.language_name_sort_key("C")[0] == languages.language_name_sort_key("Č")[0]
    assert languages.language_name_sort_key("AZ")[0] == languages.language_name_sort_key("aZ")[0]


def test_get_top_languages_name_sort_with_accented_croatian(monkeypatch):
    names = {
        "/languages/aaa": "Živi",
        "/languages/bbb": "C",
        "/languages/ccc": "Č",
        "/languages/ddd": "Ć",
        "/languages/eee": "b",
    }

    async def counts(kind, ebook_access=None):
        if kind == "work":
            return [(key, n) for n, key in enumerate(names, start=1)]
        return []

    monkeypatch.setattr(languages, "get_all_language_counts", counts)
    monkeypatch.setattr(languages, "get_language_name", lambda key, _lang: names[key])

    ordered = asyncio.run(languages.get_top_languages(50, "hr", sort="name"))
    assert [row.name for row in ordered] == ["b", "C", "Ć", "Č", "Živi"]

    # The popularity ranking and API limit remain unchanged.
    ranked = asyncio.run(languages.get_top_languages(2, "hr", sort="count"))
    assert [row.name for row in ranked] == ["b", "Ć"]
