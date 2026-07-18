"""Mirror of tests/unit/js/searchModalAuthor.test.js.

The Python port (worksearch/author_suggestion.py) and the JS source
(search-modal/authorSuggestion.js) implement the same matching rules, so these
cases are kept in lockstep with the JS test to lock parity.
"""

from openlibrary.plugins.worksearch.author_suggestion import (
    AUTHOR_SUGGESTION_MAX,
    derive_authors,
    query_matches_name,
)


def work(key, author_name=None, author_key=None):
    """Build a Solr-style work doc with a single primary author."""
    doc = {"key": key, "title": f"Work {key}"}
    if author_name:
        doc["author_name"] = [author_name]
    if author_key:
        doc["author_key"] = [author_key]
    return doc


class TestQueryMatchesName:
    def test_matches_a_surname_substring_of_the_full_name(self):
        assert query_matches_name("asimov", "Isaac Asimov") is True

    def test_matches_the_full_name_typed_out(self):
        assert query_matches_name("octavia butler", "Octavia E. Butler") is True

    def test_matches_on_a_shared_whole_word(self):
        assert query_matches_name("le guin", "Ursula K. Le Guin") is True

    def test_matches_a_query_that_is_a_prefix_of_a_name_word(self):
        assert query_matches_name("asim", "Isaac Asimov") is True
        assert query_matches_name("leo tol", "Leo Tolstoy") is True

    def test_does_not_match_a_query_mid_word_inside_a_name_token(self):
        assert query_matches_name("art", "Bart Giamatti") is False

    def test_does_not_match_a_title_that_skews_to_one_author(self):
        assert query_matches_name("dune", "Frank Herbert") is False
        assert query_matches_name("the great gatsby", "F. Scott Fitzgerald") is False

    def test_ignores_short_shared_tokens_like_particles_initials(self):
        assert query_matches_name("the de la", "Walter de la Mare") is False

    def test_folds_diacritics(self):
        assert query_matches_name("gabriel garcia marquez", "Gabriel García Márquez") is True

    def test_is_empty_safe(self):
        assert query_matches_name("", "Isaac Asimov") is False
        assert query_matches_name("asimov", "") is False
        assert query_matches_name("", "") is False


class TestDeriveAuthors:
    def test_surfaces_a_named_author_even_with_a_single_book(self):
        docs = [
            work("/works/OL1W", "Octavia E. Butler", "OL11A"),
            work("/works/OL2W", "Someone Else", "OL22A"),
        ]
        assert derive_authors(docs, "octavia butler") == [{"key": "OL11A", "name": "Octavia E. Butler"}]

    def test_surfaces_multiple_distinct_authors_for_an_ambiguous_given_name(self):
        docs = [
            work("/works/OL1W", "Stephen King", "OL19A"),
            work("/works/OL2W", "Stephen Hawking", "OL20A"),
            work("/works/OL3W", "Stephen King", "OL19A"),  # dupe key -> collapsed
        ]
        assert derive_authors(docs, "stephen") == [
            {"key": "OL19A", "name": "Stephen King"},
            {"key": "OL20A", "name": "Stephen Hawking"},
        ]

    def test_dedupes_a_prolific_author_to_a_single_row(self):
        docs = [work(f"/works/OL{i}W", "Isaac Asimov", "OL34221A") for i in range(4)]
        assert derive_authors(docs, "asimov") == [{"key": "OL34221A", "name": "Isaac Asimov"}]

    def test_caps_the_number_of_author_rows(self):
        docs = [
            work("/works/OL1W", "John Smith", "OL1A"),
            work("/works/OL2W", "Jane Smith", "OL2A"),
            work("/works/OL3W", "Adam Smith", "OL3A"),
            work("/works/OL4W", "Zadie Smith", "OL4A"),
        ]
        assert len(derive_authors(docs, "smith")) == AUTHOR_SUGGESTION_MAX

    def test_only_scans_the_top_results_not_the_whole_page(self):
        # Asimov is the 6th result -- past the scan window -- so no row.
        docs = [
            *(work(f"/works/OL{i}W", "Filler Writer", f"OL9{i}A") for i in range(5)),
            work("/works/OLaW", "Isaac Asimov", "OL34221A"),
        ]
        assert derive_authors(docs, "asimov") == []

    def test_returns_nothing_for_a_title_search(self):
        docs = [work(f"/works/OL{i}W", "Frank Herbert", "OL79034A") for i in range(5)]
        assert derive_authors(docs, "dune") == []

    def test_ignores_docs_missing_an_author_key(self):
        docs = [work("/works/OL1W", "Isaac Asimov", None)]
        assert derive_authors(docs, "asimov") == []

    def test_is_empty_safe(self):
        assert derive_authors([], "asimov") == []
        assert derive_authors(None, "asimov") == []
