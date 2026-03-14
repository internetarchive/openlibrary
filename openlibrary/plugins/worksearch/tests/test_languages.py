import unicodedata


def _sort_by_name(entries):
    """Apply the same sort key used in get_top_languages when sort='name'."""
    entries.sort(key=lambda x: unicodedata.normalize("NFD", x["name"] or "").casefold())
    return entries


def _make_entry(name, count=0):
    return {"name": name, "key": "/languages/xxx", "marc_code": "xxx", "count": count, "ebook_edition_count": 0}


def test_name_sort_is_case_insensitive():
    entries = [_make_entry("Zuni"), _make_entry("abkhaze"), _make_entry("English")]
    result = _sort_by_name(entries)
    names = [e["name"] for e in result]
    assert names == ["abkhaze", "English", "Zuni"]


def test_name_sort_places_diacritics_after_base_char():
    # 'Čeština' (Č) should sort after 'Croatian' (Cr) and before 'Danish' (D),
    # not at the end of the list as raw string comparison would put it.
    entries = [
        _make_entry("Danish"),
        _make_entry("Čeština"),
        _make_entry("Croatian"),
        _make_entry("Catalan"),
    ]
    result = _sort_by_name(entries)
    names = [e["name"] for e in result]
    # Č decomposes to C + combining caron in NFD, so it sorts after 'Croatian'
    assert names.index("Čeština") < names.index("Danish")
    assert names.index("Čeština") > names.index("Croatian")
    # And not at the end (which is what raw comparison would do)
    assert names[-1] != "Čeština"


def test_name_sort_handles_none_name():
    # Languages where get_language_name may return None
    entries = [_make_entry("Zulu"), _make_entry(None), _make_entry("Amharic")]
    result = _sort_by_name(entries)
    # Should not raise; None is treated as empty string and sorts first
    assert result[0]["name"] is None
