import pytest

from openlibrary.i18n.language_negotiation import (
    ParsedLanguagePreference,
    get_book_language_from_preferences,
    get_preferred_wikipedia_languages,
    negotiate_ui_locale,
    parse_accept_language,
)


class TestParseAcceptLanguage:
    def test_empty_header(self):
        assert parse_accept_language("") == []
        assert parse_accept_language("   ") == []

    def test_single_language(self):
        result = parse_accept_language("en")
        assert len(result) == 1
        assert result[0].tag == "en"
        assert result[0].language == "en"
        assert result[0].quality == 1.0

    def test_single_language_with_region(self):
        result = parse_accept_language("pt-BR")
        assert len(result) == 1
        assert result[0].tag == "pt-BR"
        assert result[0].language == "pt"
        assert result[0].quality == 1.0

    def test_multiple_languages_with_quality(self):
        result = parse_accept_language("pt-BR, pt;q=0.9, es-419;q=0.8, en;q=0.7")
        assert len(result) == 4
        # Should be sorted by quality descending
        assert result[0].tag == "pt-BR"
        assert result[0].quality == 1.0
        assert result[1].tag == "pt"
        assert result[1].quality == 0.9
        assert result[2].tag == "es-419"
        assert result[2].language == "es"
        assert result[2].quality == 0.8
        assert result[3].tag == "en"
        assert result[3].quality == 0.7

    def test_wildcard_ignored(self):
        result = parse_accept_language("en, *;q=0.1")
        assert len(result) == 1
        assert result[0].tag == "en"

    def test_quality_sorting(self):
        result = parse_accept_language("en;q=0.5, fr;q=0.9, de;q=0.7")
        assert result[0].language == "fr"
        assert result[1].language == "de"
        assert result[2].language == "en"

    def test_chinese_variants(self):
        result = parse_accept_language("zh-HK, zh-TW;q=0.9, zh;q=0.8, en;q=0.5")
        assert result[0].tag == "zh-HK"
        assert result[0].language == "zh"
        assert result[1].tag == "zh-TW"
        assert result[2].tag == "zh"
        assert result[3].tag == "en"

    def test_invalid_quality_defaults_to_zero(self):
        result = parse_accept_language("en;q=abc")
        assert len(result) == 1
        assert result[0].quality == 0.0

    def test_complex_real_world_header(self):
        header = "en-US,en;q=0.9,fr-FR;q=0.8,fr;q=0.7,de;q=0.6"
        result = parse_accept_language(header)
        assert len(result) == 5
        assert result[0].tag == "en-US"
        assert result[0].language == "en"
        assert result[1].tag == "en"
        assert result[2].tag == "fr-FR"
        assert result[2].language == "fr"


class TestNegotiateUiLocale:
    def test_empty_preferences(self):
        assert negotiate_ui_locale([]) is None

    def test_exact_match(self):
        prefs = parse_accept_language("fr")
        assert negotiate_ui_locale(prefs) == "fr"

    def test_region_falls_back_to_base(self):
        prefs = parse_accept_language("pt-BR")
        assert negotiate_ui_locale(prefs) == "pt"

    def test_second_preference_matched(self):
        """When first language isn't supported, should try subsequent ones."""
        prefs = parse_accept_language("xx, es;q=0.8, en;q=0.5")
        result = negotiate_ui_locale(prefs)
        assert result == "es"

    def test_chinese_maps_to_zh(self):
        prefs = parse_accept_language("zh-TW, zh;q=0.9, en;q=0.5")
        result = negotiate_ui_locale(prefs)
        assert result == "zh"

    def test_no_match_returns_none(self):
        prefs = parse_accept_language("xx, yy;q=0.8")
        result = negotiate_ui_locale(prefs, available=["en", "fr"])
        assert result is None

    def test_custom_available_locales(self):
        prefs = parse_accept_language("de, fr;q=0.8")
        result = negotiate_ui_locale(prefs, available=["fr", "en"])
        assert result == "fr"


class TestGetPreferredWikipediaLanguages:
    def test_empty_preferences(self):
        result = get_preferred_wikipedia_languages([])
        assert result == ["en"]

    def test_single_language(self):
        prefs = parse_accept_language("fr")
        result = get_preferred_wikipedia_languages(prefs)
        assert result == ["fr", "en"]

    def test_language_with_region(self):
        prefs = parse_accept_language("zh-HK")
        result = get_preferred_wikipedia_languages(prefs)
        # Should include both the full tag and the primary subtag
        assert "zh-hk" in result
        assert "zh" in result
        assert "en" in result

    def test_multiple_preferences(self):
        prefs = parse_accept_language("pt-BR, es;q=0.8, en;q=0.5")
        result = get_preferred_wikipedia_languages(prefs)
        assert result[0] == "pt-br"
        assert "pt" in result
        assert "es" in result
        assert "en" in result

    def test_english_not_duplicated(self):
        prefs = parse_accept_language("en-US, en;q=0.9")
        result = get_preferred_wikipedia_languages(prefs)
        assert result.count("en") == 1

    def test_preserves_order(self):
        prefs = parse_accept_language("fr, de;q=0.9, es;q=0.8")
        result = get_preferred_wikipedia_languages(prefs)
        fr_idx = result.index("fr")
        de_idx = result.index("de")
        es_idx = result.index("es")
        assert fr_idx < de_idx < es_idx


class TestGetBookLanguageFromPreferences:
    def test_empty_preferences(self):
        assert get_book_language_from_preferences([]) is None

    def test_returns_primary_subtag(self):
        prefs = parse_accept_language("pt-BR, en;q=0.5")
        assert get_book_language_from_preferences(prefs) == "pt"

    def test_returns_top_preference(self):
        prefs = parse_accept_language("fr;q=0.8, en;q=0.9")
        # en has higher quality, so it should be first after sorting
        assert get_book_language_from_preferences(prefs) == "en"

    def test_chinese_variant(self):
        prefs = parse_accept_language("zh-TW")
        assert get_book_language_from_preferences(prefs) == "zh"
