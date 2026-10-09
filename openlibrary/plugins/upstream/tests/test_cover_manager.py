"""The cover manager's list of images and the edit a save makes."""

from unittest.mock import MagicMock

import pytest
import web

from openlibrary.core.models import Image
from openlibrary.plugins.upstream import covers

SCAN = "https://archive.org/download/foo00bar/page"


class FakeEdition:
    def __init__(self, cover_ids, ocaid="foo00bar"):
        self.key = "/books/OL1M"
        self.type = web.storage(key="/type/edition")
        self.covers = cover_ids
        self.ocaid = ocaid
        self._site = MagicMock()
        self._site.get_many.return_value = []
        self.saves = []

    def get_covers(self):
        return [Image(self._site, "b", i) for i in self.covers]

    def _save(self, comment=None, action=None, data=None):
        self.saves.append((comment, action, data))


def info(source_url="", olid="OL1M", author="/people/ada"):
    return web.storage(source_url=source_url, olid=olid, author=author, created=MagicMock(isoformat=lambda: "2024-03-02T00:00:00"), width=600, height=900)


@pytest.fixture
def infos(monkeypatch):
    """Coverstore metadata by cover id; ids left out look missing."""
    table = {}
    monkeypatch.setattr(Image, "info", lambda self, fetch_author=True: table.get(self.id))
    return table


@pytest.fixture
def uploads(monkeypatch):
    calls = []

    def fake_upload(category, olid, **kwargs):
        calls.append(kwargs)
        return web.storage(id=500)

    monkeypatch.setattr(covers, "upload_to_coverstore", fake_upload)
    return calls


class TestCoverManagerState:
    def test_scans_come_first_and_stay_listed(self, infos):
        infos[10] = info()
        state = covers.cover_manager_state(FakeEdition([10]))
        assert [item["id"] for item in state["items"]] == ["suggestion:archive-cover", "suggestion:archive-title", "img:10"]
        assert state["current"] == "img:10"

    def test_a_copied_scan_shows_as_its_copy(self, infos):
        infos[10] = info()
        infos[20] = info(source_url=f"{SCAN}/cover")
        state = covers.cover_manager_state(FakeEdition([10, 20]))
        assert [(item["id"], item["kind"], item["removable"]) for item in state["items"]] == [
            ("img:20", "archive_cover", False),
            ("suggestion:archive-title", "archive_title", False),
            ("img:10", "upload", True),
        ]

    def test_an_edition_without_covers_shows_its_scan(self, infos):
        assert covers.cover_manager_state(FakeEdition([]))["current"] == "suggestion:archive-cover"

    def test_no_scan_no_cover(self, infos):
        assert covers.cover_manager_state(FakeEdition([], ocaid=None)) == {"key": "/books/OL1M", "current": None, "items": []}


class TestApplyCoverChanges:
    def test_picking_another_attached_image_reorders(self, infos, uploads):
        doc = FakeEdition([10, 11])
        assert covers.apply_cover_changes(doc, "img:11", [], [], None, "1.2.3.4") == 11
        assert doc.covers == [11, 10]
        assert doc.saves == [("Update covers", "update-book-covers", None)]
        assert uploads == []

    def test_a_scan_is_copied_in_and_recorded_as_added(self, infos, uploads):
        doc = FakeEdition([10])
        assert covers.apply_cover_changes(doc, "suggestion:archive-title", [], [], web.storage(key="/people/ada"), "1.2.3.4") == 500
        assert uploads == [{"source_url": f"{SCAN}/title", "author_key": "/people/ada", "ip": "1.2.3.4"}]
        assert doc.covers == [500, 10]
        assert doc.saves[0][1] == "add-cover"
        assert doc.saves[0][2] == {"url": f"{SCAN}/title"}

    def test_a_scan_already_copied_is_reused(self, infos, uploads):
        infos[20] = info(source_url=f"{SCAN}/cover")
        doc = FakeEdition([10, 20])
        assert covers.apply_cover_changes(doc, "suggestion:archive-cover", [], [], None, "1.2.3.4") == 20
        assert uploads == []
        assert doc.covers == [20, 10]

    def test_uploads_attach_and_removals_detach(self, infos, uploads):
        infos[30] = info()
        infos[31] = info()
        doc = FakeEdition([10, 11])
        covers.apply_cover_changes(doc, "img:30", [30, 31], [10], None, "1.2.3.4")
        assert doc.covers == [30, 11, 31]
        assert doc.saves[0][1] == "add-cover"

    def test_the_selection_is_never_removed(self, infos, uploads):
        doc = FakeEdition([10, 11])
        covers.apply_cover_changes(doc, "img:11", [], [11], None, "1.2.3.4")
        assert doc.covers == [11, 10]

    def test_no_change_saves_nothing(self, infos, uploads):
        doc = FakeEdition([10, 11])
        assert covers.apply_cover_changes(doc, "img:10", [], [99], None, "1.2.3.4") == 10
        assert doc.saves == []

    @pytest.mark.parametrize(
        ("selected", "added", "error"),
        [
            ("img:99", [], "not one of this book's images"),
            ("suggestion:nope", [], "Unknown suggestion"),
            ("https://example.com/x.jpg", [], "Unknown selection"),
            ("img:10", [40], "was not uploaded for /books/OL1M"),  # uploaded for another record
        ],
    )
    def test_rejects_images_that_are_not_this_books(self, infos, uploads, selected, added, error):
        infos[40] = info(olid="OL2M")
        with pytest.raises(ValueError, match=error):
            covers.apply_cover_changes(FakeEdition([10]), selected, added, [], None, "1.2.3.4")

    def test_a_failed_copy_raises(self, infos, monkeypatch):
        monkeypatch.setattr(covers, "upload_to_coverstore", lambda *a, **k: web.storage(code=3, message="Invalid URL"))
        with pytest.raises(RuntimeError, match="Invalid URL"):
            covers.apply_cover_changes(FakeEdition([10]), "suggestion:archive-cover", [], [], None, "1.2.3.4")
