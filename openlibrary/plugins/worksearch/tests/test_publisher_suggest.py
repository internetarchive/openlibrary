from types import SimpleNamespace

import web

from openlibrary.plugins.worksearch import publishers


def test_the_last_word_matches_whole_or_as_a_prefix():
    assert publishers.suggest_solr_query("penguin bo") == "publisher:(penguin (bo OR bo*))"
    assert publishers.suggest_solr_query("pengu") == "publisher:((pengu OR pengu*))"


def test_punctuation_is_not_sent_to_solr_as_syntax():
    assert publishers.suggest_solr_query('harper & row: "x"') == "publisher:(harper row (x OR x*))"
    assert publishers.suggest_solr_query("&&") == ""


def test_the_name_typed_comes_first_then_names_that_start_with_it():
    names = [("Editorial Tor", 900), ("Tor Books", 500), ("Victor Gollancz", 400), ("Tor", 30)]
    assert [s["value"] for s in publishers.rank_suggestions("tor", names, limit=10)] == ["Tor", "Tor Books", "Editorial Tor", "Victor Gollancz"]


def test_suggestions_carry_their_count_and_stop_at_the_limit():
    names = [("Penguin Books", 51), ("Penguin", 19), ("Penguin Group", 4)]
    assert publishers.rank_suggestions("Peng", names, limit=2) == [
        {"value": "Penguin Books", "count": 51},
        {"value": "Penguin", "count": 19},
    ]


def _solr_answering(names, partial=False, asked=None):
    def select(solr_q, **params):
        if asked is not None:
            asked.append((solr_q, params))
        facets = [web.storage(value=v, count=c) for v, c in names]
        return web.storage(partial=partial, facets={"publisher_facet": facets})

    return lambda: SimpleNamespace(select=select)


def test_one_capped_search_and_no_fuzzy_retry(monkeypatch):
    asked = []
    monkeypatch.setattr(publishers.search, "get_solr", _solr_answering([], asked=asked))
    assert publishers._suggest_publishers("gollanzc", 8) == []
    [(solr_q, params)] = asked
    assert solr_q == "publisher:((gollanzc OR gollanzc*))"
    assert params["timeAllowed"] == publishers.SUGGEST_TIME_ALLOWED_MS
    assert params["_pass_time_allowed"] is False


def test_an_answer_cut_short_is_shown_but_not_cached(monkeypatch):
    monkeypatch.setattr(publishers.search, "get_solr", _solr_answering([("Penguin", 19)], partial=True))
    cached = []
    monkeypatch.setattr(publishers.cache.memcache_memoize, "memcache_get", lambda self, args, kw: None)
    monkeypatch.setattr(publishers.cache.memcache_memoize, "memcache_set", lambda self, *a, **kw: cached.append(a))
    assert publishers.suggest_publishers("peng") == [{"value": "Penguin", "count": 19}]
    assert cached == []


def test_a_query_too_short_to_narrow_anything_is_not_searched(monkeypatch):
    monkeypatch.setattr(publishers, "_cached_suggest_publishers", lambda q, limit: [q, limit])
    assert publishers.suggest_publishers(" Pe ") == []
    assert publishers.suggest_publishers("Tor") == ["tor", 8]
    assert publishers.suggest_publishers("  Penguin   BOOKS ", limit=3) == ["penguin books", 3]
