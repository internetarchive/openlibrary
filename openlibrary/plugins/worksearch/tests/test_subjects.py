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

        # Should search for "thriller" (slug only), not "genrethriller"
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
        # Tag exists but is of type "subject", not "genre"
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


class TestDecorateWithAuthorPhotos:
    """Tests for subjects.decorate_with_author_photos."""

    def _make_handler(self):
        return subjects_handler()

    def _make_mock_author_thing(self, key, photo_url):
        thing = MagicMock()
        thing.key = key
        thing.get_photo_url.return_value = photo_url
        return thing

    def test_sets_photo_url_when_author_has_photo(self):
        handler = self._make_handler()
        subject = web.storage(notable_authors=[web.storage(key="/authors/OL1A", name="Isaac Asimov", count=5)])
        mock_thing = self._make_mock_author_thing("/authors/OL1A", "https://covers.openlibrary.org/a/id/1-M.jpg")

        with patch("web.ctx") as mock_ctx:
            mock_ctx.site.get_many.return_value = [mock_thing]
            handler.decorate_with_author_photos(subject)

        assert subject.notable_authors[0].photo_url == "https://covers.openlibrary.org/a/id/1-M.jpg"

    def test_falls_back_to_none_when_author_has_no_photo(self):
        """No photo on the Author thing -> photo_url is None, macro renders placeholder."""
        handler = self._make_handler()
        subject = web.storage(notable_authors=[web.storage(key="/authors/OL2A", name="Jane Doe", count=2)])
        mock_thing = self._make_mock_author_thing("/authors/OL2A", None)

        with patch("web.ctx") as mock_ctx:
            mock_ctx.site.get_many.return_value = [mock_thing]
            handler.decorate_with_author_photos(subject)

        assert subject.notable_authors[0].photo_url is None

    def test_falls_back_to_none_when_author_thing_missing(self):
        """Batch fetch didn't return a matching thing at all -> still degrades to None, no crash."""
        handler = self._make_handler()
        subject = web.storage(notable_authors=[web.storage(key="/authors/OL3A", name="Missing Author", count=1)])

        with patch("web.ctx") as mock_ctx:
            mock_ctx.site.get_many.return_value = []
            handler.decorate_with_author_photos(subject)

        assert subject.notable_authors[0].photo_url is None

    def test_no_notable_authors_is_a_noop(self):
        """Empty/missing notable_authors shouldn't trigger a get_many call at all."""
        handler = self._make_handler()
        subject = web.storage(notable_authors=[])

        with patch("web.ctx") as mock_ctx:
            handler.decorate_with_author_photos(subject)
            mock_ctx.site.get_many.assert_not_called()

    def test_missing_notable_authors_key_is_a_noop(self):
        """Subjects without the notable_authors key at all (e.g. details=False) don't crash."""
        handler = self._make_handler()
        subject = web.storage()

        with patch("web.ctx") as mock_ctx:
            handler.decorate_with_author_photos(subject)
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
