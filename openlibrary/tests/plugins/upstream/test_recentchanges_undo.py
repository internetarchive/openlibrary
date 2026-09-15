"""Tests for the undo pre-check behind internetarchive/openlibrary#5664.

Undoing an author merge fails with a 500 when the pre-merge (revision - 1)
records reference authors that have since been merged into other authors
(so their current type is /type/redirect). The undo now pre-checks this via
Changeset.get_undo_error() and flashes a message instead of attempting a save
that infobase would reject.
"""

from unittest import mock

import pytest
import web

from infogami.infobase import client
from openlibrary.plugins.upstream.recentchanges import recentchanges_view


def _save_merge_scenario(site):
    """Builds the #5664 scenario on the mock site.

    Returns the merge changeset (the one whose undo would fail).

    * rev 1: master author, duplicate author, and an edition referencing the
      duplicate.
    * the merge being undone: only the edition is rewritten to the master (the
      duplicate is deliberately *not* part of this changeset).
    * a later, separate merge: the duplicate becomes a redirect to another
      author, so its current type is /type/redirect.
    """
    # The mock_site fixture saves every type doc first, so the scenario's
    # changesets start at this index.
    base = len(site.changesets)
    site.save_many(
        [
            {"key": "/authors/master", "type": {"key": "/type/author"}, "name": "Master"},
            {"key": "/authors/dup", "type": {"key": "/type/author"}, "name": "Dup"},
            {
                "key": "/books/book1",
                "type": {"key": "/type/edition"},
                "title": "Book",
                "authors": [{"key": "/authors/dup"}],
            },
        ]
    )
    site.save_many(
        [
            {
                "key": "/books/book1",
                "type": {"key": "/type/edition"},
                "title": "Book",
                "authors": [{"key": "/authors/master"}],
            }
        ],
        action="merge-authors",
        comment="merge authors",
        data={"master": "/authors/master", "duplicates": ["/authors/dup"]},
    )
    site.save_many(
        [
            {"key": "/authors/other", "type": {"key": "/type/author"}, "name": "Other"},
            {
                "key": "/authors/dup",
                "type": {"key": "/type/redirect"},
                "location": "/authors/other",
            },
        ],
        comment="merge authors again",
    )
    return site.get_change(base + 1)


class TestGetUndoError:
    def test_reports_redirect_reference(self, mock_site):
        change = _save_merge_scenario(mock_site)

        error = change.get_undo_error()

        assert error
        assert "/books/book1" in error
        assert "/authors/dup" in error

    def test_none_when_references_are_valid(self, mock_site):
        change = _save_merge_scenario(mock_site)
        # Undo the later merge: the duplicate is a real author again.
        mock_site.save_many(
            [{"key": "/authors/dup", "type": {"key": "/type/author"}, "name": "Dup"}],
            comment="unmerge",
        )

        assert change.get_undo_error() is None

    def test_reports_missing_reference(self, mock_site):
        # rev 1 of the edition references an author that no longer exists.
        base = len(mock_site.changesets)
        mock_site.save_many(
            [
                {
                    "key": "/books/book1",
                    "type": {"key": "/type/edition"},
                    "title": "Book",
                    "authors": [{"key": "/authors/ghost"}],
                }
            ]
        )
        mock_site.save_many(
            [
                {
                    "key": "/books/book1",
                    "type": {"key": "/type/edition"},
                    "title": "Book",
                    "authors": [{"key": "/authors/master"}],
                }
            ],
            action="merge-authors",
            comment="merge authors",
            data={},
        )
        change = mock_site.get_change(base + 1)

        error = change.get_undo_error()

        assert error
        assert "/authors/ghost" in error


class TestRecentChangesViewPost:
    def _login_super_librarian(self):
        return mock.patch(
            "openlibrary.plugins.upstream.recentchanges.get_current_user",
            return_value=mock.Mock(is_super_librarian_or_higher=lambda: True),
        )

    def _post(self, id):
        # web.py's SeeOther redirect resolves the target against ctx.path.
        web.ctx.path = "/recentchanges/2014/04/04/merge-authors/%s" % id
        web.ctx.home = "http://localhost:8080"
        return recentchanges_view().POST(id)

    def test_flashes_message_when_undo_not_possible(self, mock_site):
        change = _save_merge_scenario(mock_site)

        with (
            self._login_super_librarian(),
            mock.patch("openlibrary.plugins.upstream.recentchanges.add_flash_message") as flash,
            pytest.raises(web.SeeOther),
        ):
            self._post(change.id)

        flash.assert_called_once()
        kind, message = flash.call_args[0]
        assert kind == "error"
        assert "/books/book1" in message
        # nothing was undone
        assert mock_site.get("/books/book1").dict()["authors"] == [{"key": "/authors/master"}]

    def test_undoes_when_no_error(self, mock_site):
        change = _save_merge_scenario(mock_site)
        # Undo the later merge: the duplicate is a real author again, so the
        # merge can be undone and the edition restored to its pre-merge state.
        mock_site.save_many(
            [{"key": "/authors/dup", "type": {"key": "/type/author"}, "name": "Dup"}],
            comment="unmerge",
        )

        with (
            self._login_super_librarian(),
            mock.patch("openlibrary.plugins.upstream.recentchanges.add_flash_message") as flash,
            pytest.raises(web.SeeOther),
        ):
            self._post(change.id)

        flash.assert_not_called()
        assert mock_site.get("/books/book1").dict()["authors"] == [{"key": "/authors/dup"}]

    def test_requires_super_librarian(self, mock_site):
        with (
            mock.patch(
                "openlibrary.plugins.upstream.recentchanges.get_current_user",
                return_value=mock.Mock(is_super_librarian_or_higher=lambda: False),
            ),
            pytest.raises(web.HTTPError),
        ):
            self._post(0)

    def test_flashes_generic_message_on_unexpected_failure(self, mock_site):
        change = _save_merge_scenario(mock_site)
        # Undo the later merge so the pre-check passes, but make the save itself
        # fail in a way the pre-check can't anticipate.
        mock_site.save_many(
            [{"key": "/authors/dup", "type": {"key": "/type/author"}, "name": "Dup"}],
            comment="unmerge",
        )
        with (
            mock.patch.object(change, "_undo", side_effect=client.ClientException("bad_data", "boom")),
            # POST re-fetches the change from the site; make it return the
            # prepared instance so the patched _undo is the one invoked.
            mock.patch.object(mock_site, "get_change", return_value=change),
            self._login_super_librarian(),
            mock.patch("openlibrary.plugins.upstream.recentchanges.add_flash_message") as flash,
            pytest.raises(web.SeeOther),
        ):
            self._post(change.id)

        flash.assert_called_once()
        kind, message = flash.call_args[0]
        assert kind == "error"
        assert "could not be undone" in message
