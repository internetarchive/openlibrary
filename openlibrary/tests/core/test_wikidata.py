import pytest
from unittest.mock import patch
from openlibrary.core import wikidata
from datetime import datetime, timedelta

EXAMPLE_WIKIDATA_DICT = {
    'id': "Q42",
    'type': 'str',
    'labels': {'en': ''},
    'descriptions': {'en': ''},
    'aliases': {'en': ['']},
    'statements': {'': {}},
    'sitelinks': {'': {}},
}


def createWikidataEntity(
    qid: str = "Q42", expired: bool = False
) -> wikidata.WikidataEntity:
    merged_dict = EXAMPLE_WIKIDATA_DICT.copy()
    merged_dict['id'] = qid
    updated_days_ago = wikidata.WIKIDATA_CACHE_TTL_DAYS + 1 if expired else 0
    return wikidata.WikidataEntity.from_dict(
        merged_dict, datetime.now() - timedelta(days=updated_days_ago)
    )


EXPIRED = "expired"
MISSING = "missing"
VALID_CACHE = ""


@pytest.mark.parametrize(
    "bust_cache, fetch_missing, status, expected_web_call, expected_cache_call",
    [
        # if bust_cache, always call web, never call cache
        (True, True, VALID_CACHE, True, False),
        (True, False, VALID_CACHE, True, False),
        # if not fetch_missing, only call web when expired
        (False, False, VALID_CACHE, False, True),
        (False, False, EXPIRED, True, True),
        # if fetch_missing, only call web when missing or expired
        (False, True, VALID_CACHE, False, True),
        (False, True, MISSING, True, True),
        (False, True, EXPIRED, True, True),
    ],
)
def test_get_wikidata_entity(
    bust_cache: bool,
    fetch_missing: bool,
    status: str,
    expected_web_call: bool,
    expected_cache_call: bool,
) -> None:
    with (
        patch.object(wikidata, "_get_from_cache") as mock_get_from_cache,
        patch.object(wikidata, "_get_from_web") as mock_get_from_web,
    ):
        if status == EXPIRED:
            mock_get_from_cache.return_value = createWikidataEntity(expired=True)
        elif status == MISSING:
            mock_get_from_cache.return_value = None
        else:
            mock_get_from_cache.return_value = createWikidataEntity()

        wikidata.get_wikidata_entity(
            'Q42', bust_cache=bust_cache, fetch_missing=fetch_missing
        )
        if expected_web_call:
            mock_get_from_web.assert_called_once()
        else:
            mock_get_from_web.assert_not_called()

        if expected_cache_call:
            mock_get_from_cache.assert_called_once()
        else:
            mock_get_from_cache.assert_not_called()


def test_get_wikipedia_link() -> None:
    # Create entity with both English and Spanish Wikipedia links
    entity = createWikidataEntity()
    entity.sitelinks = {
        'enwiki': {'url': 'https://en.wikipedia.org/wiki/Example'},
        'eswiki': {'url': 'https://es.wikipedia.org/wiki/Ejemplo'},
    }

    # Test getting Spanish link
    assert entity.get_wikipedia_link('es') == (
        'https://es.wikipedia.org/wiki/Ejemplo',
        'es',
    )

    # Test getting English link
    assert entity.get_wikipedia_link('en') == (
        'https://en.wikipedia.org/wiki/Example',
        'en',
    )

    # Test fallback to English when requested language unavailable
    assert entity.get_wikipedia_link('fr') == (
        'https://en.wikipedia.org/wiki/Example',
        'en',
    )

    # Test no links available
    entity_no_links = createWikidataEntity()
    entity_no_links.sitelinks = {}
    assert entity_no_links.get_wikipedia_link() is None

    # Test only non-English link available
    entity_no_english = createWikidataEntity()
    entity_no_english.sitelinks = {
        'eswiki': {'url': 'https://es.wikipedia.org/wiki/Ejemplo'}
    }
    assert entity_no_english.get_wikipedia_link('es') == (
        'https://es.wikipedia.org/wiki/Ejemplo',
        'es',
    )
    assert entity_no_english.get_wikipedia_link('en') is None


def test_get_statement_values() -> None:
    entity = createWikidataEntity()

    # Test with single value
    entity.statements = {'P2038': [{'value': {'content': 'Chris-Wiggins'}}]}
    assert entity.get_statement_values('P2038') == ['Chris-Wiggins']

    # Test with multiple values
    entity.statements = {
        'P2038': [
            {'value': {'content': 'Value1'}},
            {'value': {'content': 'Value2'}},
            {'value': {'content': 'Value3'}},
        ]
    }
    assert entity.get_statement_values('P2038') == ['Value1', 'Value2', 'Value3']

    # Test with missing property
    assert entity.get_statement_values('P9999') == []

    # Test with malformed statement (missing value or content)
    entity.statements = {
        'P2038': [
            {'value': {'content': 'Valid'}},
            {'wrong_key': {}},  # Missing 'value'
            {'value': {}},  # Missing 'content'
        ]
    }
    assert entity.get_statement_values('P2038') == ['Valid']
