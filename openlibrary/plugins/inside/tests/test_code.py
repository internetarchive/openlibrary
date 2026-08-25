from openlibrary.core.fulltext import build_fulltext_query


def test_no_filters_returns_query_unchanged():
    assert build_fulltext_query("moby dick") == "moby dick"
    assert build_fulltext_query('"exact phrase"') == '"exact phrase"'
    assert build_fulltext_query("moby dick", languages=[], readable=False) == "moby dick"


def test_language_adds_anded_clause():
    assert build_fulltext_query("moby dick", ["French"]) == '(moby dick) AND languageSorter:"French"'


def test_multiple_languages_are_ored():
    assert build_fulltext_query("moby dick", ["French", "German"]) == '(moby dick) AND (languageSorter:"French" OR languageSorter:"German")'


def test_user_query_is_parenthesized():
    # The user's own OR must not swallow the language clause.
    assert build_fulltext_query("cat OR dog", ["German"]) == '(cat OR dog) AND languageSorter:"German"'


def test_quotes_stripped_from_language_value():
    # A quote in the facet value can't break out of its clause.
    assert build_fulltext_query("whale", ['Fre"nch']) == '(whale) AND languageSorter:"French"'


def test_blank_language_values_dropped():
    assert build_fulltext_query("whale", ["", "  "]) == "whale"


def test_readable_adds_collection_clause():
    assert build_fulltext_query("whale", readable=True) == "(whale) AND (collection:(inlibrary) OR (!collection:(printdisabled)))"


def test_language_and_readable_compose():
    assert (
        build_fulltext_query("whale", ["French"], readable=True)
        == '(whale) AND languageSorter:"French" AND (collection:(inlibrary) OR (!collection:(printdisabled)))'
    )
