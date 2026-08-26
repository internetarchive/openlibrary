from openlibrary.core.fulltext import build_fulltext_query, filter_readable


def test_no_filters_returns_query_unchanged():
    assert build_fulltext_query("moby dick") == "moby dick"
    assert build_fulltext_query('"exact phrase"') == '"exact phrase"'
    assert build_fulltext_query("moby dick", languages=[]) == "moby dick"


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


def hit(ocaid: str) -> dict:
    return {"fields": {"identifier": [ocaid]}}


def test_readable_keeps_public_and_borrowable():
    hits = [hit("public"), hit("borrowable"), hit("restricted")]
    availability = {
        "public": {"is_readable": True, "is_lendable": False},
        "borrowable": {"is_readable": False, "is_lendable": True},
        "restricted": {"is_readable": False, "is_lendable": False, "is_printdisabled": True},
    }
    assert [h["fields"]["identifier"][0] for h in filter_readable(hits, availability)] == ["public", "borrowable"]


def test_readable_drops_hits_with_no_availability_record():
    # An unknown scan can't be shown as readable — but see the fail-open case
    # below: that's about the lookup failing wholesale, not one missing entry.
    assert filter_readable([hit("unknown")], {"other": {"is_readable": True}}) == []


def test_readable_fails_open_when_availability_lookup_failed():
    # Better a page of unfiltered results than an empty page.
    hits = [hit("public"), hit("restricted")]
    assert filter_readable(hits, {}) == hits
