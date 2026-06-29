"""Tests for openlibrary.plugins.worksearch.subjects."""

from unittest.mock import MagicMock, patch

import pytest
import web

from openlibrary.plugins.worksearch.subjects import SubjectEngine, build_browse_threads
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


class TestBuildBrowseThreads:
    """Curation of place/person/time facets into 'Keep exploring' browse seeds."""

    @staticmethod
    def _facets(*names):
        return [web.storage(key=f"/subjects/x:{n}", name=n, count=1) for n in names]

    def _subj(self, name="Science fiction", **facets):
        return web.storage(name=name, **facets)

    def test_strips_qualifiers_and_caps_each_group(self):
        subj = self._subj(
            places=self._facets("Mars (Planet)", "Outer space", "London", "Earth", "England", "Moon", "Venus"),
        )
        groups = build_browse_threads(subj)
        place_group = next(g for g in groups if g["kind"] == "places")
        names = [i.display_name for i in place_group["items"]]
        assert names == ["Mars", "Outer space", "London", "Earth", "England", "Moon"]  # capped at 6, qualifier stripped

    def test_dedupes_across_article_and_qualifier(self):
        subj = self._subj(
            people=self._facets("Doctor (Fictitious character)", "Doctor", "Han Solo (Fictitious character)", "Han Solo", "Leia Organa"),
        )
        groups = build_browse_threads(subj)
        people = next(g for g in groups if g["kind"] == "people")
        assert [i.display_name for i in people["items"]] == ["Doctor", "Han Solo", "Leia Organa"]

    def test_drops_self_reference_and_generic_noise(self):
        subj = self._subj(
            name="Fiction",
            subjects=self._facets("Fiction", "Fiction, general"),
            places=self._facets("Mars", "Earth", "Moon"),
        )
        groups = build_browse_threads(subj)
        assert all(g["kind"] != "subjects" for g in groups)  # 'subjects' never a browse-thread kind
        assert {g["kind"] for g in groups} == {"places"}

    def test_times_drops_bare_eras_and_tautological_words_then_self_hides(self):
        subj = self._subj(
            times=self._facets("20th century", "Future", "The Future", "The Far Future", "1950-"),
        )
        # After dropping centuries/year-ranges, bare "Future"/"The Future" (generic),
        # only "The Far Future" survives -> below min_items -> group omitted.
        assert build_browse_threads(subj) == []

    def test_times_renders_when_enough_named_eras_survive(self):
        subj = self._subj(
            times=self._facets("Victorian era", "World War II", "Middle Ages", "20th century"),
        )
        groups = build_browse_threads(subj)
        times = next(g for g in groups if g["kind"] == "times")
        assert [i.display_name for i in times["items"]] == ["Victorian era", "World War II", "Middle Ages"]

    def test_empty_facets_yield_no_groups(self):
        assert build_browse_threads(self._subj(places=[], people=[], times=[])) == []
