"""Tests for locale-aware sorting of language names (#11962)."""

from typing import Literal
from unittest.mock import AsyncMock, patch

import pytest

from openlibrary.plugins.worksearch import languages


async def _get_sorted(
    user_lang: str,
    sort: Literal["count", "name", "ebook_edition_count"],
    names: dict[str, str],
    counts: list[tuple[str, int]],
):
    source = AsyncMock(side_effect=lambda solr_type, ebook_access=None: counts if solr_type == "work" else [])
    with (
        patch.object(languages, "get_all_language_counts", source),
        patch.object(languages, "get_language_name", lambda key, lang: names[key]),
    ):
        return await languages.get_top_languages(500, user_lang=user_lang, sort=sort)


class TestGetTopLanguagesNameSort:
    @pytest.mark.asyncio
    async def test_croatian_diacritics_sort_with_base_letter(self):
        # In hr, č is a letter of its own that follows all plain "c" words,
        # instead of being dumped at the end of the list (#11962).
        names = {
            "/languages/dan": "Dansk",
            "/languages/ces": "Čeština",
            "/languages/cat": "Català",
            "/languages/cym": "Cymraeg",
        }
        counts = [("/languages/dan", 10), ("/languages/ces", 9), ("/languages/cat", 8), ("/languages/cym", 7)]

        results = await _get_sorted("hr", "name", names, counts)

        assert [r.name for r in results] == ["Català", "Cymraeg", "Čeština", "Dansk"]

    @pytest.mark.asyncio
    async def test_sort_order_depends_on_user_locale(self):
        # ö is a separate letter that follows z in Swedish, but is treated
        # as "o" in English — each user gets their own locale's order.
        names = {"/languages/zul": "Zulu", "/languages/ola": "Öland"}
        counts = [("/languages/zul", 10), ("/languages/ola", 9)]

        swedish = await _get_sorted("sv", "name", names, counts)
        english = await _get_sorted("en", "name", names, counts)

        assert [r.name for r in swedish] == ["Zulu", "Öland"]
        assert [r.name for r in english] == ["Öland", "Zulu"]

    @pytest.mark.asyncio
    async def test_case_does_not_affect_order(self):
        names = {"/languages/eng": "english", "/languages/epo": "ESPERANTO"}
        counts = [("/languages/eng", 10), ("/languages/epo", 9)]

        results = await _get_sorted("en", "name", names, counts)

        assert [r.name for r in results] == ["english", "ESPERANTO"]

    @pytest.mark.asyncio
    async def test_count_sort_still_works(self):
        names = {"/languages/eng": "English", "/languages/epo": "Esperanto"}
        counts = [("/languages/eng", 5), ("/languages/epo", 100)]

        results = await _get_sorted("en", "count", names, counts)

        assert [r.key for r in results] == ["/languages/epo", "/languages/eng"]


class TestGetCollator:
    def test_collator_is_cached_per_locale(self):
        assert languages._get_collator("hr") is languages._get_collator("hr")
        assert languages._get_collator("hr") is not languages._get_collator("sv")

    def test_primary_strength_ignores_case_and_diacritics(self):
        collator = languages._get_collator("en")

        assert collator.getSortKey("Čeština") == collator.getSortKey("cestina")
        assert collator.getSortKey("Français") == collator.getSortKey("FRANCAIS")

    def test_unknown_locale_does_not_crash(self):
        collator = languages._get_collator("zz_QQ")

        assert collator.getSortKey("abc")
