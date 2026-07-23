"""Tests for openlibrary.plugins.worksearch.subjects."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import web

from openlibrary.plugins.worksearch.code import SearchResponse
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


class TestGetSubjectAsyncSolrError:
    """Reproduces #13192: a Solr-error sentinel must not silently propagate as a crash."""

    def _make_engine(self):
        return SubjectEngine(
            name="subject",
            key="subjects",
            prefix="/subjects/",
            facet="subject_facet",
            facet_key="subject_key",
        )

    @pytest.mark.asyncio
    async def test_solr_error_sets_subject_error_and_leaves_work_count_none(self):
        engine = self._make_engine()
        error_response = SearchResponse(
            facet_counts=None,
            sort="new",
            docs=[],
            num_found=None,
            solr_select="select?q=subject_key:fiction",
            error="Solr is down",
            time=0.1,
        )

        with (
            patch(
                "openlibrary.plugins.worksearch.code.run_solr_query_async",
                new=AsyncMock(return_value=error_response),
            ),
            patch(
                "openlibrary.plugins.worksearch.subjects.add_availability_async",
                new=AsyncMock(return_value=[]),
            ),
        ):
            subject = await engine.get_subject_async("/subjects/fiction")

        assert subject.error == "Solr is down"
        assert subject.work_count is None


class TestSubjectsGetSolrError:
    """Reproduces #13192 at the handler level: a Solr error must render an explicit
    "unavailable" state (503), not the crash-prone "subjects" template nor the
    misleading "not found" (404) template used for a genuine zero-result subject."""

    def _make_handler(self):
        return subjects_handler()

    def test_solr_error_renders_unavailable_not_crash(self):
        handler = self._make_handler()
        error_subject = web.storage(
            name="fiction",
            subject_type="subject",
            solr_query="subject_key:fiction",
            work_count=None,
            error="Solr is down",
        )

        with (
            patch(
                "openlibrary.plugins.worksearch.subjects.get_subject",
                return_value=error_subject,
            ),
            patch("openlibrary.plugins.worksearch.subjects.render_template") as mock_render,
            patch("web.ctx") as mock_ctx,
            patch("web.input", return_value=web.storage(sort="readinglog")),
        ):
            handler.GET("/subjects/fiction")

        mock_render.assert_called_once_with("subjects/unavailable.tmpl", "/subjects/fiction")
        assert mock_ctx.status == "503 Service Unavailable"

    def test_solr_connection_failure_with_no_error_message_still_renders_unavailable(self):
        """A total Solr connection failure/timeout -- the "cold cache" trigger described
        in #13192 -- leaves result.error itself None (see execute_solr_query_async's
        httpx.HTTPError handling), so the branch must key off work_count, not error."""
        handler = self._make_handler()
        error_subject = web.storage(
            name="fiction",
            subject_type="subject",
            solr_query="subject_key:fiction",
            work_count=None,
            error=None,
        )

        with (
            patch(
                "openlibrary.plugins.worksearch.subjects.get_subject",
                return_value=error_subject,
            ),
            patch("openlibrary.plugins.worksearch.subjects.render_template") as mock_render,
            patch("web.ctx") as mock_ctx,
            patch("web.input", return_value=web.storage(sort="readinglog")),
        ):
            handler.GET("/subjects/fiction")

        mock_render.assert_called_once_with("subjects/unavailable.tmpl", "/subjects/fiction")
        assert mock_ctx.status == "503 Service Unavailable"

    def test_zero_work_count_without_error_still_renders_notfound(self):
        """Regression: a genuine zero-result subject (no Solr error) must still 404."""
        handler = self._make_handler()
        empty_subject = web.storage(
            name="nonexistent",
            subject_type="subject",
            solr_query="subject_key:nonexistent",
            work_count=0,
            error=None,
        )

        with (
            patch(
                "openlibrary.plugins.worksearch.subjects.get_subject",
                return_value=empty_subject,
            ),
            patch("openlibrary.plugins.worksearch.subjects.render_template") as mock_render,
            patch("web.ctx") as mock_ctx,
            patch("web.input", return_value=web.storage(sort="readinglog")),
        ):
            handler.GET("/subjects/nonexistent")

        mock_render.assert_called_once_with("subjects/notfound.tmpl", "/subjects/nonexistent")
        assert mock_ctx.status == "404 Not Found"
