import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

mock_icu = MagicMock()
mock_collator = MagicMock()
mock_icu.Collator = MagicMock()
mock_icu.Collator.PRIMARY = 1
mock_icu.Collator.createInstance.return_value = mock_collator
mock_icu.Locale = MagicMock()


def mock_get_sort_key(text):
    if text == "Curaçao":
        return b"A"
    elif text == "Čeština":
        return b"B"
    elif text == "Dansk":
        return b"C"
    return b""


mock_collator.getSortKey.side_effect = mock_get_sort_key


@pytest.mark.asyncio
async def test_get_top_languages_sorting_with_icu():
    mock_all_counts = AsyncMock(
        side_effect=lambda solr_type, ebook_access=None: (
            [
                ("/languages/hrv", 10),
                ("/languages/ces", 5),
                ("/languages/dan", 3),
            ]
            if solr_type == "work"
            else [("/languages/hrv", 2), ("/languages/ces", 1)]
        )
    )

    mock_names = {
        "/languages/hrv": "Curaçao",
        "/languages/ces": "Čeština",
        "/languages/dan": "Dansk",
    }

    with patch.dict(sys.modules, {"icu": mock_icu}):
        from openlibrary.plugins.worksearch import languages

        with (
            patch(
                "openlibrary.plugins.worksearch.languages.get_all_language_counts",
                mock_all_counts,
            ),
            patch(
                "openlibrary.plugins.worksearch.languages.get_language_name",
                lambda key, lang: mock_names.get(key, key),
            ),
        ):
            res = await languages.get_top_languages(limit=3, user_lang="hr", sort="name")

            mock_icu.Collator.createInstance.assert_called_with(mock_icu.Locale("hr"))
            mock_collator.setStrength.assert_called_with(mock_icu.Collator.PRIMARY)

            names = [x.name for x in res]
            assert names[0] == "Curaçao"
            assert names[1] == "Čeština"
            assert names[2] == "Dansk"


@pytest.mark.asyncio
async def test_get_top_languages_fallback():
    mock_all_counts = AsyncMock(
        side_effect=lambda solr_type, ebook_access=None: (
            [
                ("/languages/hrv", 10),
                ("/languages/ces", 5),
                ("/languages/dan", 3),
            ]
            if solr_type == "work"
            else [("/languages/hrv", 2), ("/languages/ces", 1)]
        )
    )

    mock_names = {
        "/languages/hrv": "Curaçao",
        "/languages/ces": "Čeština",
        "/languages/dan": "Dansk",
    }

    with patch.dict(sys.modules, {"icu": None}):
        from openlibrary.plugins.worksearch import languages

        with (
            patch(
                "openlibrary.plugins.worksearch.languages.get_all_language_counts",
                mock_all_counts,
            ),
            patch(
                "openlibrary.plugins.worksearch.languages.get_language_name",
                lambda key, lang: mock_names.get(key, key),
            ),
        ):
            res = await languages.get_top_languages(limit=3, user_lang="hr", sort="name")

            names = [x.name for x in res]
            assert names[0] == "Curaçao"
            assert names[1] == "Dansk"
            assert names[2] == "Čeština"
