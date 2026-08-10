"""Tests for openlibrary.plugins.worksearch.subjects."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import web

from openlibrary.plugins.worksearch.code import SearchResponse
from openlibrary.plugins.worksearch.subjects import (
    MAX_NOTABLE_AUTHORS,
    SubjectEngine,
    merge_notable_authors,
    normalize_author_name,
)
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
        subject = web.storage(key="/subjects/science_fiction", subject_type="subject")
        cached = [
            {
                "key": "/authors/OL1A",
                "name": "Isaac Asimov",
                "representative_work": {"title": "Foundation"},
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

    def test_cache_failure_degrades_to_empty_list(self):
        """A solr/memcache/infobase failure hides the widget instead of 500ing the page."""
        handler = self._make_handler()
        engine = self._make_engine()
        subject = web.storage(key="/subjects/science_fiction", subject_type="subject")

        with (
            patch("openlibrary.plugins.worksearch.subjects.SUBJECTS", [engine]),
            patch(
                "openlibrary.plugins.worksearch.subjects.get_cached_notable_authors",
                side_effect=OSError("memcache is down"),
            ),
        ):
            handler.decorate_with_notable_authors(subject)

        assert subject.notable_authors == []

    def test_stale_cache_shape_degrades_to_empty_list(self):
        """
        memcache entries have no expiry and the key_prefix is stable across
        deploys, so a payload written in an older shape can outlive the change.
        Rehydrating it must hide the widget, not 500 the page.
        """
        handler = self._make_handler()
        engine = self._make_engine()
        subject = web.storage(key="/subjects/science_fiction", subject_type="subject")
        cached = [{"name": "Isaac Asimov"}]  # no "key": a shape we no longer write

        with (
            patch("openlibrary.plugins.worksearch.subjects.SUBJECTS", [engine]),
            patch(
                "openlibrary.plugins.worksearch.subjects.get_cached_notable_authors",
                return_value=cached,
            ),
        ):
            handler.decorate_with_notable_authors(subject)

        assert subject.notable_authors == []

    def test_no_representative_work_stays_none(self):
        handler = self._make_handler()
        engine = self._make_engine()
        subject = web.storage(key="/subjects/x", subject_type="subject", authors=[])
        cached = [{"key": "/authors/OL2A", "name": "Jane Doe", "representative_work": None}]

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

    def test_unknown_subject_type_sets_empty_list(self):
        """No matching SubjectEngine (shouldn't normally happen) -> bail, widget doesn't render."""
        handler = self._make_handler()
        subject = web.storage(key="/subjects/x", subject_type="nonexistent", authors=[])

        with patch("openlibrary.plugins.worksearch.subjects.SUBJECTS", []):
            handler.decorate_with_notable_authors(subject)

        assert subject.notable_authors == []


class TestComputeNotableAuthors:
    """Tests for the memcache_memoize sync seam (Phase 1, epic #13135).

    _compute_notable_authors is what actually gets cached by
    get_cached_notable_authors -- it bridges the async Solr-ranking call.
    """

    def _make_engine(self, name="subject", prefix="/subjects/"):
        return SubjectEngine(name=name, key="subjects", prefix=prefix, facet="subject_facet", facet_key="subject_key")

    def test_returns_plain_json_encodable_dicts(self):
        """memcache round-trips through JSON, so the cached payload must be dicts."""
        from openlibrary.plugins.worksearch.subjects import _compute_notable_authors

        engine = self._make_engine()
        stub_author = web.storage(
            key="/authors/OL1A",
            name="Isaac Asimov",
            representative_work=web.storage(title="Foundation"),
        )

        with (
            patch("openlibrary.plugins.worksearch.subjects.SUBJECTS", [engine]),
            patch("web.ctx") as mock_ctx,
            patch.object(engine, "get_notable_authors_async", return_value=[stub_author]),
        ):
            mock_ctx.__contains__ = lambda self, key: key == "site"
            result = _compute_notable_authors("subject", "science_fiction")

        assert result == [
            {
                "key": "/authors/OL1A",
                "name": "Isaac Asimov",
                "representative_work": {"title": "Foundation"},
            }
        ]
        assert isinstance(result[0], dict)

    def test_unknown_subject_type_returns_empty_list(self):
        from openlibrary.plugins.worksearch.subjects import _compute_notable_authors

        with patch("openlibrary.plugins.worksearch.subjects.SUBJECTS", []):
            result = _compute_notable_authors("nonexistent", "x")

        assert result == []

    def test_no_authors_found_returns_empty_list(self):
        from openlibrary.plugins.worksearch.subjects import _compute_notable_authors

        engine = self._make_engine()

        with (
            patch("openlibrary.plugins.worksearch.subjects.SUBJECTS", [engine]),
            patch("web.ctx") as mock_ctx,
            patch.object(engine, "get_notable_authors_async", return_value=[]),
        ):
            mock_ctx.__contains__ = lambda self, key: key == "site"
            result = _compute_notable_authors("subject", "obscure_subject")

        assert result == []


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
            authors = await engine.get_notable_authors_async("science_fiction")

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
            authors = await engine.get_notable_authors_async("science_fiction")

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
            authors = await engine.get_notable_authors_async("obscure_subject")

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
            authors = await engine.get_notable_authors_async("science_fiction")

        assert len(authors) == 1
        assert authors[0].name == "Author Three"

    @pytest.mark.asyncio
    async def test_only_the_first_author_of_a_work_is_used(self):
        """author_key carries no role, so trailing entries (illustrators, narrators) are skipped."""
        engine = self._make_engine()
        docs = [
            {
                "key": "/works/OL1W",
                "title": "The Boy Who Harnessed the Wind",
                "author_key": ["OL1A", "OL2A", "OL3A"],
                "author_name": ["William Kamkwamba", "Bryan Mealer", "Anna Hymas"],
            }
        ]
        mock_result = self._make_solr_result(docs)

        with patch(
            "openlibrary.plugins.worksearch.code.run_solr_query_async",
            return_value=mock_result,
        ):
            authors = await engine.get_notable_authors_async("irrigation")

        assert [a.name for a in authors] == ["William Kamkwamba"]

    @pytest.mark.asyncio
    async def test_samples_each_signal_concurrently(self):
        """One query per signal in NOTABLE_AUTHORS_SORTS, each with the candidate filter."""
        from openlibrary.plugins.worksearch import subjects as subjects_module

        engine = self._make_engine()
        mock_result = self._make_solr_result([])

        with patch(
            "openlibrary.plugins.worksearch.code.run_solr_query_async",
            return_value=mock_result,
        ) as mock_query:
            await engine.get_notable_authors_async("science_fiction")

        calls = mock_query.call_args_list
        assert [c.kwargs["sort"] for c in calls] == list(subjects_module.NOTABLE_AUTHORS_SORTS)
        for call in calls:
            assert call.kwargs["extra_params"] == [("fq", subjects_module.NOTABLE_AUTHORS_CANDIDATE_FILTER)]

    @pytest.mark.asyncio
    async def test_query_is_labelled_for_solr_monitoring(self):
        """Defaults to its own ol.label so this query is attributable in Solr load monitoring."""
        engine = self._make_engine()
        mock_result = self._make_solr_result([])

        with patch(
            "openlibrary.plugins.worksearch.code.run_solr_query_async",
            return_value=mock_result,
        ) as mock_query:
            await engine.get_notable_authors_async("science_fiction")

        assert mock_query.call_args.kwargs["request_label"] == "SUBJECT_NOTABLE_AUTHORS"


class TestMergeNotableAuthors:
    """Tests for subjects.merge_notable_authors, which blends the per-signal samples."""

    def _doc(self, n, keys=None, names=None, title=None):
        return {
            "key": f"/works/OL{n}W",
            "title": title or f"Book {n}",
            "author_key": keys or [f"OL{n}A"],
            "author_name": names or [f"Author {n}"],
        }

    def test_interleaves_samples_by_rank(self):
        """Rank 0 of every sample comes before rank 1, so a thin signal still gets represented."""
        osp = [self._doc(1, ["OL1A"], ["Peskin"]), self._doc(2, ["OL2A"], ["Weinberg"])]
        readinglog = [self._doc(3, ["OL3A"], ["Carroll"]), self._doc(4, ["OL4A"], ["McTaggart"])]

        authors = merge_notable_authors([osp, readinglog])

        assert [a.name for a in authors] == ["Peskin", "Carroll", "Weinberg", "McTaggart"]

    def test_dedupes_the_same_author_across_samples(self):
        """An author present in both samples appears once, keeping their highest-ranked work."""
        osp = [self._doc(1, ["OL1A"], ["Peskin"], title="Intro to QFT")]
        readinglog = [self._doc(2, ["OL1A"], ["Peskin"], title="Some Other Book")]

        authors = merge_notable_authors([osp, readinglog])

        assert len(authors) == 1
        assert authors[0].representative_work.title == "Intro to QFT"

    def test_dedupes_duplicate_author_records_by_name(self):
        """Distinct OLIDs for one person ("Mctaggart" vs "McTaggart") render as one card."""
        docs = [
            self._doc(1, ["OL1A"], ["Lynne McTaggart"]),
            self._doc(2, ["OL2A"], ["Lynne Mctaggart"]),
        ]

        authors = merge_notable_authors([docs])

        assert [a.name for a in authors] == ["Lynne McTaggart"]

    def test_dedupes_duplicate_author_records_in_non_latin_scripts(self):
        """The dedupe has to hold on /subjects/russian_literature too, not just Latin names."""
        docs = [
            self._doc(1, ["OL1A"], ["Лев Толстой"]),
            self._doc(2, ["OL2A"], ["лев толстой"]),
            self._doc(3, ["OL3A"], ["Антон Чехов"]),
        ]

        authors = merge_notable_authors([docs])

        assert [a.name for a in authors] == ["Лев Толстой", "Антон Чехов"]

    def test_skips_authors_with_blank_names(self):
        """The solr updater defaults a missing name to "", which would render a nameless card."""
        docs = [self._doc(1, ["OL1A"], [""]), self._doc(2, ["OL2A"], ["Real Author"])]

        authors = merge_notable_authors([docs])

        assert [a.name for a in authors] == ["Real Author"]

    def test_skips_docs_with_no_authors(self):
        docs = [
            {"key": "/works/OL1W", "title": "Untitled Government Resolution"},
            self._doc(2, ["OL2A"], ["Real Author"]),
        ]

        authors = merge_notable_authors([docs])

        assert [a.name for a in authors] == ["Real Author"]

    def test_stops_at_max_notable_authors(self):
        docs = [self._doc(i) for i in range(MAX_NOTABLE_AUTHORS + 5)]

        authors = merge_notable_authors([docs])

        assert len(authors) == MAX_NOTABLE_AUTHORS

    def test_handles_one_empty_sample(self):
        """A subject with no osp data at all still produces a list from the other signal."""
        readinglog = [self._doc(1, ["OL1A"], ["Only Signal"])]

        authors = merge_notable_authors([[], readinglog])

        assert [a.name for a in authors] == ["Only Signal"]

    def test_all_samples_empty_returns_empty_list(self):
        assert merge_notable_authors([[], []]) == []


class TestNormalizeAuthorName:
    def test_collapses_case_and_punctuation(self):
        assert normalize_author_name("Lynne McTaggart") == normalize_author_name("lynne mctaggart")
        assert normalize_author_name("A. M. Michael") == normalize_author_name("A M Michael")

    def test_distinct_names_stay_distinct(self):
        assert normalize_author_name("Isaac Asimov") != normalize_author_name("Ray Bradbury")

    def test_collapses_accents(self):
        assert normalize_author_name("José Saramago") == normalize_author_name("Jose Saramago")

    def test_non_latin_scripts_survive(self):
        """An ASCII-only strip would empty these, and an empty value skips the dedupe."""
        assert normalize_author_name("Лев Толстой") != ""
        assert normalize_author_name("村上春樹") != ""

    def test_non_latin_scripts_still_dedupe(self):
        assert normalize_author_name("Лев Толстой") == normalize_author_name("лев толстой")
        assert normalize_author_name("Лев Толстой") != normalize_author_name("Антон Чехов")


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

    async def _get_subject_with_error(self, error):
        engine = self._make_engine()
        error_response = SearchResponse(
            facet_counts=None,
            sort="new",
            docs=[],
            num_found=None,
            solr_select="select?q=subject_key:fiction",
            error=error,
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
            return await engine.get_subject_async("/subjects/fiction", details=True)

    @pytest.mark.asyncio
    async def test_solr_error_sets_subject_error_and_leaves_work_count_none(self):
        subject = await self._get_subject_with_error("Solr is down")

        assert subject.error == "Solr is down"
        assert subject.work_count is None

    @pytest.mark.asyncio
    async def test_solr_error_defaults_detail_fields_so_template_macros_dont_crash(self):
        """subjects.html and its macros (PublishingHistory, RelatedSubjects) read
        page.publishing_history/subjects/places/people/times unconditionally.
        Those are only populated inside the `if details and result.facet_counts:`
        block, which is skipped whenever Solr errors (facet_counts is None) --
        so without a default, rendering the page on the error path would crash
        on one of these instead. (Notable authors are unaffected --
        decorate_with_notable_authors already defaults/fetches independently.)"""
        subject = await self._get_subject_with_error(None)

        assert subject.publishing_history == []
        assert subject.subjects == []
        assert subject.places == []
        assert subject.people == []
        assert subject.times == []


class TestSubjectsGetSolrError:
    """Reproduces #13192 at the handler level: a Solr error must render the normal
    "subjects" page (degraded, 503) rather than crash -- not a separate template."""

    def _make_handler(self):
        return subjects_handler()

    def _get_with_error_subject(self, error):
        handler = self._make_handler()
        error_subject = web.storage(
            name="fiction",
            subject_type="subject",
            solr_query="subject_key:fiction",
            work_count=None,
            error=error,
            publishing_history=[],
            subjects=[],
            places=[],
            people=[],
            times=[],
        )

        with (
            patch(
                "openlibrary.plugins.worksearch.subjects.get_subject",
                return_value=error_subject,
            ),
            patch("openlibrary.plugins.worksearch.subjects.render_template") as mock_render,
            patch("openlibrary.plugins.worksearch.subjects.subjects.decorate_with_tags"),
            patch("openlibrary.plugins.worksearch.subjects.subjects.decorate_with_notable_authors"),
            patch("web.ctx") as mock_ctx,
            patch("web.input", return_value=web.storage(sort="readinglog")),
        ):
            handler.GET("/subjects/fiction")

        return mock_render, mock_ctx, error_subject

    def test_solr_error_renders_normal_page_degraded_not_crash(self):
        mock_render, mock_ctx, error_subject = self._get_with_error_subject("Solr is down")

        mock_render.assert_called_once_with("subjects", page=error_subject)
        assert mock_ctx.status == "503 Service Unavailable"

    def test_solr_connection_failure_with_no_error_message_still_renders_normal_page(self):
        """A total Solr connection failure/timeout -- the "cold cache" trigger described
        in #13192 -- leaves result.error itself None (see execute_solr_query_async's
        httpx.HTTPError handling), so the branch must key off work_count, not error."""
        mock_render, mock_ctx, error_subject = self._get_with_error_subject(None)

        mock_render.assert_called_once_with("subjects", page=error_subject)
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
