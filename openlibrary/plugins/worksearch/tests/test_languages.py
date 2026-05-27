from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from openlibrary.plugins.worksearch import languages


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

    mock_collator = MagicMock()

    # Mock getSortKey to return custom keys to test Croatian sorting
    def mock_get_sort_key(text):
        if text == "Curaçao":
            return b"A"
        elif text == "Čeština":
            return b"B"
        elif text == "Dansk":
            return b"C"
        return b""

    mock_collator.getSortKey.side_effect = mock_get_sort_key

    # Mock Collator and its static methods/attributes at the module level
    mock_collator_class = MagicMock()
    mock_collator_class.createInstance.return_value = mock_collator
    mock_collator_class.PRIMARY = 1

    with (
        patch(
            "openlibrary.plugins.worksearch.languages.Collator",
            mock_collator_class,
        ),
        patch(
            "openlibrary.plugins.worksearch.languages.Locale"
        ) as mock_locale,
        patch(
            "openlibrary.plugins.worksearch.languages.get_all_language_counts",
            mock_all_counts,
        ),
        patch(
            "openlibrary.plugins.worksearch.languages.get_language_name",
            lambda key, lang: mock_names.get(key, key),
        ),
    ):

        res = await languages.get_top_languages(
            limit=3, user_lang="hr", sort="name"
        )

        # Check Collator was created and set correctly
        mock_collator_class.createInstance.assert_called_once()
        mock_locale.assert_called_with("hr")

        # Check sort order: Curaçao, Čeština, Dansk
        names = [x.name for x in res]
        assert names[0] == "Curaçao"
        assert names[1] == "Čeština"
        assert names[2] == "Dansk"