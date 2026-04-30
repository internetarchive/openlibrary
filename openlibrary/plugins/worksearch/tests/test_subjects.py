"""Tests for openlibrary.plugins.worksearch.subjects."""

from unittest.mock import MagicMock, patch

import web

from openlibrary.plugins.worksearch.subjects import subjects as subjects_handler


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
