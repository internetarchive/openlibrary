"""Tests for openlibrary.plugins.worksearch.subjects."""

from unittest.mock import MagicMock, patch

import pytest
import web

from openlibrary.plugins.worksearch.subjects import SubjectEngine
from openlibrary.plugins.worksearch.subjects import subjects as subjects_handler


class TestFacetWrapper:
    def test_invalid_subject_facet_includes_value_in_error(self):
        engine = SubjectEngine(
            name="subject",
            key="subjects",
            prefix="/subjects/",
            facet="subject_facet",
            facet_key="subject_key",
        )
        with patch("openlibrary.plugins.worksearch.subjects.SUBJECTS", []), pytest.raises(AssertionError, match="subject_facet"):
            engine.facet_wrapper("subject_facet", "some_value", "Some Label", 5)


class TestDecorateWithTags:
    """Tests for subjects.decorate_with_tags."""

    def _make_handler(self):
        return subjects_handler()

    def _make_mock_tag(self, name, tag_type, key="/tags/OL1T"):
        tag = MagicMock()
        tag.name = name
        tag.tag_type = tag_type
        tag.key = key
        return tag

    def test_genre_prefix_finds_tag_by_slug(self):
        """decorate_with_tags strips 'genre:' prefix and searches for the bare slug."""
        handler = self._make_handler()
        subject = web.storage(name="genre:thriller", subject_type="subject")
        mock_tag = self._make_mock_tag("Thriller", "genre")

        with (
            patch(
                "openlibrary.plugins.worksearch.subjects.Tag.find",
                return_value=[mock_tag.key],
            ) as mock_find,
            patch("web.ctx") as mock_ctx,
        ):
            mock_ctx.site.get_many.return_value = [mock_tag]
            handler.decorate_with_tags(subject)

        mock_find.assert_called_once_with("thriller")
        assert subject.tag == mock_tag

    def test_plain_subject_name_uses_full_slug(self):
        """decorate_with_tags normalizes a plain subject name and uses subject_type."""
        handler = self._make_handler()
        subject = web.storage(name="science fiction", subject_type="subject")
        mock_tag = self._make_mock_tag("Science Fiction", "subject")

        with (
            patch(
                "openlibrary.plugins.worksearch.subjects.Tag.find",
                return_value=[mock_tag.key],
            ) as mock_find,
            patch("web.ctx") as mock_ctx,
        ):
            mock_ctx.site.get_many.return_value = [mock_tag]
            handler.decorate_with_tags(subject)

        mock_find.assert_called_once_with("science_fiction")
        assert subject.tag == mock_tag

    def test_no_tags_found_leaves_subject_unchanged(self):
        """decorate_with_tags does nothing when Tag.find returns empty list."""
        handler = self._make_handler()
        subject = web.storage(name="genre:mystery", subject_type="subject")

        with patch(
            "openlibrary.plugins.worksearch.subjects.Tag.find",
            return_value=[],
        ):
            handler.decorate_with_tags(subject)

        assert not hasattr(subject, "tag")
        assert not hasattr(subject, "disambiguations")

    def test_wrong_type_tag_goes_to_disambiguations(self):
        """A tag whose type doesn't match is added to disambiguations, not subject.tag."""
        handler = self._make_handler()
        subject = web.storage(name="genre:horror", subject_type="subject")
        mock_tag = self._make_mock_tag("Horror", "subject")

        with (
            patch(
                "openlibrary.plugins.worksearch.subjects.Tag.find",
                return_value=[mock_tag.key],
            ),
            patch("web.ctx") as mock_ctx,
        ):
            mock_ctx.site.get_many.return_value = [mock_tag]
            handler.decorate_with_tags(subject)

        assert not hasattr(subject, "tag")
        assert mock_tag in subject.disambiguations

    def test_content_format_prefix_finds_tag_by_slug(self):
        """decorate_with_tags handles 'content_format:' prefix correctly."""
        handler = self._make_handler()
        subject = web.storage(name="content_format:graphic_novel", subject_type="subject")
        mock_tag = self._make_mock_tag("Graphic Novel", "content_format")

        with (
            patch(
                "openlibrary.plugins.worksearch.subjects.Tag.find",
                return_value=[mock_tag.key],
            ) as mock_find,
            patch("web.ctx") as mock_ctx,
        ):
            mock_ctx.site.get_many.return_value = [mock_tag]
            handler.decorate_with_tags(subject)

        mock_find.assert_called_once_with("graphic_novel")
        assert subject.tag == mock_tag


class TestDecorateWithNotableAuthors:
    """Tests for subjects.decorate_with_notable_authors (Phase 1, epic #13135).

    decorate_with_notable_authors reads from get_cached_notable_authors
    (memcache_memoize-wrapped), which returns plain dicts (memcache
    round-trips through JSON) -- so these tests check both the cache-read
    path and the rehydration back into web.storage the Templetor macro needs.
    """

    def _make_handler(self):
        return subjects_handler()

    def _make_engine(self, name="subject", prefix="/subjects/"):
        return SubjectEngine(name=name, key="subjects", prefix=prefix, facet="subject_facet", facet_key="subject_key")

    def test_rehydrates_cached_dicts_into_storage(self):
        """Cached raw dicts (incl. nested representative_work) come back as web.storage, not bare dicts."""
        handler = self._make_handler()
        engine = self._make_engine()
        subject = web.storage(
            key="/subjects/science_fiction",
            subject_type="subject",
            authors=[web.storage(key="/authors/OL1A", name="Isaac Asimov", count=7)],
        )
        cached = [
            {
                "key": "/authors/OL1A",
                "name": "Isaac Asimov",
                "photo_url": "https://covers.openlibrary.org/a/id/1-M.jpg",
                "representative_work": {"key": "/works/OL1W", "title": "Foundation", "cover_id": 12345},
                "count": 1,
            }
        ]

        with (
            patch("openlibrary.plugins.worksearch.subjects.SUBJECTS", [engine]),
            patch(
                "openlibrary.plugins.worksearch.subjects.get_cached_notable_authors",
                return_value=cached,
            ),
        ):
            handler.decorate_with_notable_authors(subject)

        author = subject.notable_authors[0]
        assert isinstance(author, web.storage)
        assert author.name == "Isaac Asimov"
        assert isinstance(author.representative_work, web.storage)
        assert author.representative_work.title == "Foundation"
        assert author.representative_work.cover_id == 12345

    def test_merges_exact_count_from_facet_not_cache(self):
        """subject.authors (fresh every request) overrides the possibly-stale cached count."""
        handler = self._make_handler()
        engine = self._make_engine()
        subject = web.storage(
            key="/subjects/science_fiction",
            subject_type="subject",
            authors=[web.storage(key="/authors/OL1A", name="Isaac Asimov", count=42)],
        )
        cached = [
            {
                "key": "/authors/OL1A",
                "name": "Isaac Asimov",
                "photo_url": None,
                "representative_work": None,
                "count": 1,
            }
        ]

        with (
            patch("openlibrary.plugins.worksearch.subjects.SUBJECTS", [engine]),
            patch(
                "openlibrary.plugins.worksearch.subjects.get_cached_notable_authors",
                return_value=cached,
            ),
        ):
            handler.decorate_with_notable_authors(subject)

        assert subject.notable_authors[0].count == 42

    def test_no_representative_work_stays_none(self):
        handler = self._make_handler()
        engine = self._make_engine()
        subject = web.storage(key="/subjects/x", subject_type="subject", authors=[])
        cached = [{"key": "/authors/OL2A", "name": "Jane Doe", "photo_url": None, "representative_work": None, "count": 3}]

        with (
            patch("openlibrary.plugins.worksearch.subjects.SUBJECTS", [engine]),
            patch(
                "openlibrary.plugins.worksearch.subjects.get_cached_notable_authors",
                return_value=cached,
            ),
        ):
            handler.decorate_with_notable_authors(subject)

        assert subject.notable_authors[0].representative_work is None

    def test_empty_cache_result_sets_empty_list(self):
        handler = self._make_handler()
        engine = self._make_engine()
        subject = web.storage(key="/subjects/obscure", subject_type="subject", authors=[])

        with (
            patch("openlibrary.plugins.worksearch.subjects.SUBJECTS", [engine]),
            patch(
                "openlibrary.plugins.worksearch.subjects.get_cached_notable_authors",
                return_value=[],
            ),
        ):
            handler.decorate_with_notable_authors(subject)

        assert subject.notable_authors == []

    def test_unknown_subject_type_leaves_subject_unchanged(self):
        """No matching SubjectEngine (shouldn't normally happen) -> bail without setting notable_authors."""
        handler = self._make_handler()
        subject = web.storage(key="/subjects/x", subject_type="nonexistent", authors=[])

        with patch("openlibrary.plugins.worksearch.subjects.SUBJECTS", []):
            handler.decorate_with_notable_authors(subject)

        assert not hasattr(subject, "notable_authors")


class TestComputeNotableAuthorsWithPhotos:
    """Tests for the memcache_memoize sync seam (Phase 1, epic #13135).

    _compute_notable_authors_with_photos is what actually gets cached by
    get_cached_notable_authors -- it bridges the async Solr-ranking call
    and folds in photo decoration so both are cached together.
    """

    def _make_engine(self, name="subject", prefix="/subjects/"):
        return SubjectEngine(name=name, key="subjects", prefix=prefix, facet="subject_facet", facet_key="subject_key")

    def _make_mock_author_thing(self, key, photo_url):
        thing = MagicMock()
        thing.key = key
        thing.get_photo_url.return_value = photo_url
        return thing

    def test_returns_plain_dicts_with_photo_urls(self):
        from openlibrary.plugins.worksearch.subjects import _compute_notable_authors_with_photos

        engine = self._make_engine()
        stub_author = web.storage(
            key="/authors/OL1A",
            name="Isaac Asimov",
            representative_work=web.storage(key="/works/OL1W", title="Foundation", cover_id=1),
            count=1,
        )
        mock_thing = self._make_mock_author_thing("/authors/OL1A", "https://covers.openlibrary.org/a/id/1-M.jpg")

        with (
            patch("openlibrary.plugins.worksearch.subjects.SUBJECTS", [engine]),
            patch("web.ctx") as mock_ctx,
            patch.object(engine, "get_notable_authors_async", return_value=[stub_author]),
        ):
            mock_ctx.__contains__ = lambda self, key: key == "site"
            mock_ctx.site.get_many.return_value = [mock_thing]
            result = _compute_notable_authors_with_photos("subject", "science_fiction")

        assert result == [
            {
                "key": "/authors/OL1A",
                "name": "Isaac Asimov",
                "representative_work": {"key": "/works/OL1W", "title": "Foundation", "cover_id": 1},
                "count": 1,
                "photo_url": "https://covers.openlibrary.org/a/id/1-M.jpg",
            }
        ]
        assert isinstance(result[0], dict)

    def test_unknown_subject_type_returns_empty_list(self):
        from openlibrary.plugins.worksearch.subjects import _compute_notable_authors_with_photos

        with patch("openlibrary.plugins.worksearch.subjects.SUBJECTS", []):
            result = _compute_notable_authors_with_photos("nonexistent", "x")

        assert result == []

    def test_no_authors_found_returns_empty_list(self):
        from openlibrary.plugins.worksearch.subjects import _compute_notable_authors_with_photos

        engine = self._make_engine()

        with (
            patch("openlibrary.plugins.worksearch.subjects.SUBJECTS", [engine]),
            patch("web.ctx") as mock_ctx,
            patch.object(engine, "get_notable_authors_async", return_value=[]),
        ):
            mock_ctx.__contains__ = lambda self, key: key == "site"
            result = _compute_notable_authors_with_photos("subject", "obscure_subject")

        assert result == []
        mock_ctx.site.get_many.assert_not_called()


class TestGetNotableAuthorsAsync:
    """Tests for SubjectEngine.get_notable_authors_async (Phase 1, epic #13135)."""

    def _make_engine(self):
        return SubjectEngine(
            name="subject",
            key="subjects",
            prefix="/subjects/",
            facet="subject_facet",
            facet_key="subject_facet",
        )

    def _make_solr_result(self, docs):
        result = MagicMock()
        result.docs = docs
        return result

    @pytest.mark.asyncio
    async def test_picks_first_occurrence_as_representative_work(self):
        """Sample is pre-sorted by signal; an author's first-seen work is their representative work."""
        engine = self._make_engine()
        docs = [
            {"key": "/works/OL1W", "title": "Foundation", "author_key": ["OL1A"], "author_name": ["Isaac Asimov"]},
            {"key": "/works/OL2W", "title": "I, Robot", "author_key": ["OL1A"], "author_name": ["Isaac Asimov"]},
        ]
        mock_result = self._make_solr_result(docs)

        with patch(
            "openlibrary.plugins.worksearch.code.run_solr_query_async",
            return_value=mock_result,
        ):
            authors = await engine.get_notable_authors_async("science_fiction", {})

        assert len(authors) == 1
        assert authors[0].name == "Isaac Asimov"
        assert authors[0].representative_work.title == "Foundation"

    @pytest.mark.asyncio
    async def test_stops_at_max_notable_authors(self):
        """Scanning stops once MAX_NOTABLE_AUTHORS unique authors are found."""
        from openlibrary.plugins.worksearch import subjects as subjects_module

        engine = self._make_engine()
        docs = [
            {
                "key": f"/works/OL{i}W",
                "title": f"Book {i}",
                "author_key": [f"OL{i}A"],
                "author_name": [f"Author {i}"],
            }
            for i in range(subjects_module.MAX_NOTABLE_AUTHORS + 5)
        ]
        mock_result = self._make_solr_result(docs)

        with patch(
            "openlibrary.plugins.worksearch.code.run_solr_query_async",
            return_value=mock_result,
        ):
            authors = await engine.get_notable_authors_async("science_fiction", {})

        assert len(authors) == subjects_module.MAX_NOTABLE_AUTHORS

    @pytest.mark.asyncio
    async def test_no_matching_works_returns_empty_list(self):
        """Graceful fallback: a sparse/under-configured subject shouldn't error out."""
        engine = self._make_engine()
        mock_result = self._make_solr_result([])

        with patch(
            "openlibrary.plugins.worksearch.code.run_solr_query_async",
            return_value=mock_result,
        ):
            authors = await engine.get_notable_authors_async("obscure_subject", {})

        assert authors == []

    @pytest.mark.asyncio
    async def test_skips_docs_missing_key_or_title(self):
        """A malformed/incomplete Solr doc (no key or no title) can't be a representative work -- skip it."""
        engine = self._make_engine()
        docs = [
            {"title": "No Key Here", "author_key": ["OL1A"], "author_name": ["Author One"]},
            {"key": "/works/OL2W", "author_key": ["OL2A"], "author_name": ["Author Two"]},
            {"key": "/works/OL3W", "title": "Valid Work", "author_key": ["OL3A"], "author_name": ["Author Three"]},
        ]
        mock_result = self._make_solr_result(docs)

        with patch(
            "openlibrary.plugins.worksearch.code.run_solr_query_async",
            return_value=mock_result,
        ):
            authors = await engine.get_notable_authors_async("science_fiction", {})

        assert len(authors) == 1
        assert authors[0].name == "Author Three"

    @pytest.mark.asyncio
    async def test_multi_author_work_does_not_overshoot_cap(self):
        """A single co-authored work that would push past MAX_NOTABLE_AUTHORS mid-doc must stop exactly at the cap."""
        from openlibrary.plugins.worksearch import subjects as subjects_module

        engine = self._make_engine()
        docs = [{"key": f"/works/OL{i}W", "title": f"Book {i}", "author_key": [f"OL{i}A"], "author_name": [f"Author {i}"]} for i in range(6)]
        docs.append(
            {
                "key": "/works/OL_COAUTHORED_W",
                "title": "Co-authored Anthology",
                "author_key": ["OL100A", "OL101A", "OL102A", "OL103A"],
                "author_name": ["Co Author A", "Co Author B", "Co Author C", "Co Author D"],
            }
        )
        mock_result = self._make_solr_result(docs)

        with patch(
            "openlibrary.plugins.worksearch.code.run_solr_query_async",
            return_value=mock_result,
        ):
            authors = await engine.get_notable_authors_async("science_fiction", {})

        assert len(authors) == subjects_module.MAX_NOTABLE_AUTHORS

    @pytest.mark.asyncio
    async def test_cover_id_included_in_representative_work(self):
        """cover_i from Solr flows into representative_work.cover_id for the SubjectAuthors macro's cover thumbnail."""
        engine = self._make_engine()
        docs = [
            {
                "key": "/works/OL1W",
                "title": "Foundation",
                "author_key": ["OL1A"],
                "author_name": ["Isaac Asimov"],
                "cover_i": 123456,
            }
        ]
        mock_result = self._make_solr_result(docs)

        with patch(
            "openlibrary.plugins.worksearch.code.run_solr_query_async",
            return_value=mock_result,
        ):
            authors = await engine.get_notable_authors_async("science_fiction", {})

        assert authors[0].representative_work.cover_id == 123456

    @pytest.mark.asyncio
    async def test_missing_cover_id_is_none(self):
        """No cover_i on the Solr doc -> cover_id is None, macro omits the cover thumbnail."""
        engine = self._make_engine()
        docs = [{"key": "/works/OL1W", "title": "Flatland", "author_key": ["OL1A"], "author_name": ["Edwin Abbott Abbott"]}]
        mock_result = self._make_solr_result(docs)

        with patch(
            "openlibrary.plugins.worksearch.code.run_solr_query_async",
            return_value=mock_result,
        ):
            authors = await engine.get_notable_authors_async("science_fiction", {})

        assert authors[0].representative_work.cover_id is None
