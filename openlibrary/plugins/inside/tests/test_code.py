from openlibrary.plugins.inside.code import build_fulltext_query


def test_no_language_returns_query_unchanged():
    assert build_fulltext_query("moby dick") == "moby dick"
    assert build_fulltext_query('"exact phrase"') == '"exact phrase"'


def test_language_adds_anded_clause():
    assert build_fulltext_query("moby dick", "French") == '(moby dick) AND languageSorter:"French"'


def test_user_query_is_parenthesized():
    # The user's own OR must not swallow the language clause.
    assert build_fulltext_query("cat OR dog", "German") == '(cat OR dog) AND languageSorter:"German"'


def test_quotes_stripped_from_language_value():
    # A quote in the facet value can't break out of its clause.
    assert build_fulltext_query("whale", 'Fre"nch') == '(whale) AND languageSorter:"French"'
