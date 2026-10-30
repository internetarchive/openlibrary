"""The cover manager's list of images and the edit a save makes."""

from unittest.mock import MagicMock

import pytest
import web

from openlibrary.core.models import Image
from openlibrary.plugins.upstream import covers

SCAN = "https://archive.org/download/foo00bar/page"


class FakeEdition:
    def __init__(self, cover_ids, ocaid="foo00bar", isbn10=None):
        self.key = "/books/OL1M"
        self.type = web.storage(key="/type/edition")
        self.covers = cover_ids
        self.ocaid = ocaid
        self.isbn10 = isbn10
        self._site = MagicMock()
        self._site.get_many.return_value = []
        self.saves = []

    def get_covers(self):
        return [Image(self._site, "b", i) for i in self.covers]

    def get_isbn10(self):
        return self.isbn10

    def _save(self, comment=None, action=None, data=None):
        self.saves.append((comment, action, data))


class FakeWork(FakeEdition):
    def __init__(self, cover_ids):
        super().__init__(cover_ids, ocaid=None)
        self.key = "/works/OL1W"
        self.type = web.storage(key="/type/work")

    def get_covers(self, use_solr=True):
        return [Image(self._site, "w", i) for i in self.covers]


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
        assert [(item["id"], item["kind"]) for item in state["items"]] == [
            ("img:20", "archive_cover"),
            ("suggestion:archive-title", "archive_title"),
            ("img:10", "upload"),
        ]

    def test_an_edition_without_covers_shows_its_scan(self, infos):
        assert covers.cover_manager_state(FakeEdition([]))["current"] == "suggestion:archive-cover"

    def test_no_scan_no_cover(self, infos):
        assert covers.cover_manager_state(FakeEdition([], ocaid=None)) == {"key": "/books/OL1M", "current": None, "items": []}

    def test_an_isbn_10_offers_amazons_cover_first(self, infos):
        items = covers.cover_manager_state(FakeEdition([], isbn10="0140449132"))["items"]
        assert [i["id"] for i in items] == ["suggestion:amazon", "suggestion:archive-cover", "suggestion:archive-title"]
        assert items[0]["thumb"] == "https://m.media-amazon.com/images/P/0140449132.01.L.jpg"
        assert items[0]["isbn"] == "0140449132"

    def test_a_copied_amazon_cover_keeps_its_isbn(self, infos):
        infos[20] = info(source_url="https://m.media-amazon.com/images/P/0140449132.01.L.jpg")
        items = covers.cover_manager_state(FakeEdition([20], ocaid=None, isbn10="0140449132"))["items"]
        assert [(i["id"], i["kind"], i["isbn"]) for i in items] == [("img:20", "amazon", "0140449132")]


def apply(doc, *, added=(), removed=(), user=None, **selection):
    return covers.apply_cover_changes(doc, added=list(added), removed=list(removed), user=user, ip="1.2.3.4", **selection)


class TestApplyCoverChanges:
    def test_picking_another_attached_image_reorders(self, infos, uploads):
        doc = FakeEdition([10, 11])
        assert apply(doc, image_id=11) == 11
        assert doc.covers == [11, 10]
        assert doc.saves == [("Update covers", "update-book-covers", None)]
        assert uploads == []

    def test_a_scan_is_copied_in_and_recorded_as_added(self, infos, uploads):
        doc = FakeEdition([10])
        assert apply(doc, suggestion="archive-title", user=web.storage(key="/people/ada")) == 500
        assert uploads == [{"source_url": f"{SCAN}/title", "author_key": "/people/ada", "ip": "1.2.3.4"}]
        assert doc.covers == [500, 10]
        assert doc.saves[0][1] == "add-cover"
        assert doc.saves[0][2] == {"url": f"{SCAN}/title"}

    def test_a_scan_already_copied_is_reused(self, infos, uploads):
        infos[20] = info(source_url=f"{SCAN}/cover")
        doc = FakeEdition([10, 20])
        assert apply(doc, suggestion="archive-cover") == 20
        assert uploads == []
        assert doc.covers == [20, 10]

    def test_uploads_attach_and_removals_detach(self, infos, uploads):
        infos[30] = info()
        infos[31] = info()
        doc = FakeEdition([10, 11])
        apply(doc, image_id=30, added=[30, 31], removed=[10])
        assert doc.covers == [30, 11, 31]
        assert doc.saves[0][1] == "add-cover"

    def test_an_upload_that_is_not_the_cover_is_still_an_add(self, infos, uploads):
        infos[30] = info()
        doc = FakeEdition([10])
        apply(doc, image_id=10, added=[30])
        assert doc.covers == [10, 30]
        assert doc.saves[0][0].endswith("/b/id/30-S.jpg")
        assert doc.saves[0][1] == "add-cover"

    def test_a_work_cover_comment_points_at_the_work_category(self, infos, uploads):
        infos[30] = info(olid="OL1W")
        doc = FakeWork([10])
        apply(doc, image_id=30, added=[30])
        assert doc.covers == [30, 10]
        assert doc.saves[0][0].endswith("/w/id/30-S.jpg")

    def test_the_selection_is_never_removed(self, infos, uploads):
        doc = FakeEdition([10, 11])
        apply(doc, image_id=11, removed=[11])
        assert doc.covers == [11, 10]

    def test_a_replacement_keeps_its_reason(self, infos, uploads):
        doc = FakeEdition([10, 11])
        apply(doc, image_id=11, reason="other", reason_note="  Movie tie-in  ")
        assert doc.saves == [("Update covers", "update-book-covers", {"reason": "other", "reason_note": "Movie tie-in"})]

    def test_a_copied_replacement_keeps_its_reason_beside_the_url(self, infos, uploads):
        doc = FakeEdition([10])
        apply(doc, suggestion="archive-cover", reason="wrong")
        assert doc.saves[0][2] == {"url": f"{SCAN}/cover", "reason": "wrong"}

    def test_a_reason_without_a_new_cover_is_dropped(self, infos, uploads):
        infos[30] = info()
        doc = FakeEdition([10])
        apply(doc, image_id=10, added=[30], reason="wrong")
        assert doc.saves[0][2] == {"url": None}

    def test_rejects_an_unknown_reason_before_copying(self, infos, uploads):
        with pytest.raises(ValueError, match="Unknown reason"):
            apply(FakeEdition([10]), suggestion="archive-cover", reason="bored")
        assert uploads == []

    def test_no_change_saves_nothing(self, infos, uploads):
        doc = FakeEdition([10, 11])
        assert apply(doc, image_id=10, removed=[99]) == 10
        assert doc.saves == []

    @pytest.mark.parametrize(
        ("selection", "added", "error"),
        [
            ({"image_id": 99}, [], "not one of /books/OL1M's images"),
            ({"suggestion": "nope"}, [], "Unknown suggestion"),
            ({"suggestion": "wikidata"}, [], "Unknown suggestion"),  # an author's, not an edition's
            ({"image_id": 10}, [40], "was not uploaded for /books/OL1M"),  # uploaded for another record
        ],
    )
    def test_rejects_images_that_are_not_this_books(self, infos, uploads, selection, added, error):
        infos[40] = info(olid="OL2M")
        with pytest.raises(ValueError, match=error):
            apply(FakeEdition([10]), added=added, **selection)

    def test_a_failed_copy_raises(self, infos, monkeypatch):
        monkeypatch.setattr(covers, "upload_to_coverstore", lambda *a, **k: web.storage(code=3, message="Invalid URL"))
        with pytest.raises(RuntimeError, match="Invalid URL"):
            apply(FakeEdition([10]), suggestion="archive-cover")
