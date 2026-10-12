"""Tests for reading the home page's genres from the editable /config/home doc, with a file
fallback (#13893). A bad or missing doc must never blank the homepage."""

import logging

import pytest

from openlibrary.plugins.openlibrary import home_genres

# A minimal but valid /config/home `genres` value, with a marker slug that is NOT in the bundled
# home_genres.json, so "doc used" and "file used" are distinguishable.
DOC_GENRES = [
    {
        "name": "Marker",
        "slug": "zz-marker",
        "kind": "genre",
        "query": "marker*",
        "count": 5000,
        "children": [
            {"name": "Submarker", "slug": "zz-sub", "query": "sub*", "count": 50},
            {"name": "Thin", "slug": "zz-thin", "query": "thin*", "count": 5},  # below MIN_SUBGENRE
        ],
    },
]


@pytest.fixture(autouse=True)
def _reset_cache():
    """The node cache is a process-global TTL; keep tests independent of each other and of order."""
    home_genres.reset_genres_cache()
    yield
    home_genres.reset_genres_cache()


class TestValidation:
    def test_well_formed_doc_is_valid(self):
        assert home_genres._valid_genres(DOC_GENRES)

    @pytest.mark.parametrize(
        "bad",
        [
            None,  # not a list
            {},  # not a list
            [],  # empty
            "nope",  # not a list
            [{"name": "x", "slug": "x", "kind": "genre", "query": "x*", "count": 1}],  # no children
            [{"slug": "x", "kind": "genre", "query": "x*", "count": 1, "children": []}],  # no name
            [{"name": "x", "slug": "x", "kind": "genre", "query": "x*", "count": "1", "children": []}],  # count str
            [{"name": "x", "slug": "x", "kind": "genre", "query": "x*", "count": 1, "children": {}}],  # children dict
            [  # a child is missing a required key
                {
                    "name": "x",
                    "slug": "x",
                    "kind": "genre",
                    "query": "x*",
                    "count": 1,
                    "children": [{"name": "c", "slug": "c", "count": 1}],  # no query
                }
            ],
        ],
    )
    def test_malformed_values_are_rejected(self, bad):
        assert not home_genres._valid_genres(bad)


class TestNodeResolution:
    """`_load_home_genre_nodes` is the uncached resolver: doc when valid, else the bundled file."""

    def test_valid_config_is_used_over_the_file(self, monkeypatch):
        monkeypatch.setattr(home_genres, "_config_home_genres", lambda: DOC_GENRES)
        assert home_genres._load_home_genre_nodes() == DOC_GENRES

    def test_missing_config_falls_back_to_the_file_quietly(self, monkeypatch, caplog):
        monkeypatch.setattr(home_genres, "_config_home_genres", lambda: None)
        with caplog.at_level(logging.ERROR, logger="openlibrary.home_genres"):
            nodes = home_genres._load_home_genre_nodes()
        assert {"action", "adventure"} <= {n["slug"] for n in nodes}  # from the bundled file
        assert "zz-marker" not in {n["slug"] for n in nodes}
        assert caplog.records == []  # a missing doc is not an error

    def test_malformed_config_falls_back_to_the_file_with_an_error(self, monkeypatch, caplog):
        malformed = [{"name": "x", "slug": "x", "kind": "genre", "query": "x*"}]  # no count/children
        monkeypatch.setattr(home_genres, "_config_home_genres", lambda: malformed)
        with caplog.at_level(logging.ERROR, logger="openlibrary.home_genres"):
            nodes = home_genres._load_home_genre_nodes()
        assert {"action", "adventure"} <= {n["slug"] for n in nodes}
        assert "x" not in {n["slug"] for n in nodes}
        assert any(r.levelno == logging.ERROR and "/config/home" in r.getMessage() for r in caplog.records)

    def test_a_read_that_raises_falls_back_to_the_file(self, monkeypatch, caplog):
        def boom():
            raise RuntimeError("infobase down")

        monkeypatch.setattr(home_genres, "_config_home_genres", boom)
        with caplog.at_level(logging.ERROR, logger="openlibrary.home_genres"):
            nodes = home_genres._load_home_genre_nodes()
        assert {"action", "adventure"} <= {n["slug"] for n in nodes}
        assert any(r.levelno >= logging.ERROR for r in caplog.records)


class TestLoadHomeGenres:
    """The public loader applies the MIN_* filtering and children→subgenres transform on top."""

    def test_doc_genres_are_filtered_and_transformed(self, monkeypatch):
        monkeypatch.setattr(home_genres, "_config_home_genres", lambda: DOC_GENRES)
        genres = home_genres.load_home_genres()
        assert [g["slug"] for g in genres] == ["zz-marker"]
        # The below-threshold child (count 5 < MIN_SUBGENRE_READABLE) is dropped; the 50 stays.
        assert [s["slug"] for s in genres[0]["subgenres"]] == ["zz-sub"]

    def test_malformed_config_still_yields_genres_from_the_file(self, monkeypatch):
        """The homepage still renders genres: the loader is non-empty and find_genre resolves."""
        monkeypatch.setattr(home_genres, "_config_home_genres", lambda: {"garbage": True})
        genres = home_genres.load_home_genres()
        assert len(genres) > 0
        assert home_genres.find_genre("action") is not None


class TestFingerprint:
    """home.get_cached_featured_genres keys its day cache on this, so an edit busts it at once."""

    def test_changes_when_the_config_changes(self, monkeypatch):
        monkeypatch.setattr(home_genres, "load_home_genre_nodes", lambda: DOC_GENRES)
        first = home_genres.genres_fingerprint()
        edited = [{**DOC_GENRES[0], "count": DOC_GENRES[0]["count"] + 1}]
        monkeypatch.setattr(home_genres, "load_home_genre_nodes", lambda: edited)
        assert home_genres.genres_fingerprint() != first

    def test_stable_for_the_same_config(self, monkeypatch):
        monkeypatch.setattr(home_genres, "load_home_genre_nodes", lambda: DOC_GENRES)
        assert home_genres.genres_fingerprint() == home_genres.genres_fingerprint()


class TestTTLCache:
    def test_value_is_held_until_reset(self, monkeypatch):
        calls = []

        def counting():
            calls.append(1)
            return DOC_GENRES

        monkeypatch.setattr(home_genres, "_load_home_genre_nodes", counting)
        home_genres.reset_genres_cache()
        home_genres.load_home_genre_nodes()
        home_genres.load_home_genre_nodes()
        assert len(calls) == 1  # second call served from the TTL cache
        home_genres.reset_genres_cache()
        home_genres.load_home_genre_nodes()
        assert len(calls) == 2


class TestInfogamiRoundTrip:
    """The nested genre nodes must come back from infogami as plain dicts, matching the file."""

    def test_config_home_genres_reads_nested_plain_dicts(self, mock_site):
        mock_site.quicksave("/config/home", "/type/object", genres=DOC_GENRES)
        assert home_genres._config_home_genres() == DOC_GENRES

    def test_no_doc_returns_none(self, mock_site):
        assert home_genres._config_home_genres() is None

    def test_doc_without_genres_key_returns_none(self, mock_site):
        mock_site.quicksave("/config/home", "/type/object", note="no genres here")
        assert home_genres._config_home_genres() is None
