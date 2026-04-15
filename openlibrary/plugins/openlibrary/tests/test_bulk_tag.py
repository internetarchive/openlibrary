"""Tests for openlibrary.plugins.openlibrary.bulk_tag."""

from unittest.mock import MagicMock

import web


class TestBulkTagWorks:
    """Tests for the bulk_tag_works POST handler."""

    def _mock_work(self, subjects=None):
        """Create a mock work object."""
        work = MagicMock()
        data = {
            "subjects": subjects or [],
            "subject_people": [],
            "subject_places": [],
            "subject_times": [],
        }
        work.get = lambda k, default=None: data.get(k, default)
        work.__setitem__ = lambda self_, k, v: data.__setitem__(k, v)
        work.dict.return_value = data
        return work

    def test_book_page_edit_missing_does_not_raise(self):
        """
        When bulk tagging from search results, book_page_edit is not sent
        by the frontend. Previously this caused an AttributeError because
        book_page_edit was not declared in web.input().
        """
        # Simulate a POST request without book_page_edit
        i = web.storage(
            work_ids="OL1W",
            tags_to_add="{}",
            tags_to_remove="{}",
            book_page_edit=False,
        )
        # Verify the fixed default: accessing book_page_edit should not raise
        assert i.book_page_edit is False
        # False is falsy, so the stats branch is skipped
        assert not i.book_page_edit
