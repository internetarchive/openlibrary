from datetime import datetime
from types import SimpleNamespace
from typing import cast

import pytest

from openlibrary.core.lists.model import List, Seed, ThingReferenceDict


def test_seed_with_string():
    lst = List(None, "/list/OL1L", None)
    seed = Seed(lst, "subject/Politics and government")
    assert seed._list == lst
    assert seed.value == "subject/Politics and government"
    assert seed.key == "subject/Politics and government"
    assert seed.type == "subject"


def test_seed_with_nonstring():
    lst = List(None, "/list/OL1L", None)
    not_a_string = cast(ThingReferenceDict, {"key": "not_a_string.key"})
    seed = Seed.from_json(lst, not_a_string)
    assert seed._list == lst
    assert seed.key == "not_a_string.key"
    assert hasattr(seed, "type") is False


def test_seed_from_json_with_blank_key():
    """Test that Seed.from_json rejects blank keys.

    Attempting to create a Seed with a blank key
    should raise a ValueError.
    """
    lst = List(None, "/list/OL1L", None)

    # Blank keys should now raise ValueError
    with pytest.raises(ValueError, match="Seed key cannot be empty"):
        Seed.from_json(lst, {"key": ""})


def test_seed_from_json_with_valid_key():
    """Test that Seed.from_json works correctly with valid keys."""
    lst = List(None, "/list/OL1L", None)
    seed = Seed.from_json(lst, {"key": "/books/OL1M"})
    assert seed.key == "/books/OL1M"


def test_list_add_seed_with_blank_key():
    """Test that List.add_seed rejects seeds with blank keys.

    Add_seed should validate that the seed key is
    non-empty before adding it to the list.
    """
    # Create a mock list with seeds
    lst = List(
        None,
        "/people/test/lists/OL1L",
        {
            "key": "/people/test/lists/OL1L",
            "type": {"key": "/type/list"},
            "name": "Test List",
            "seeds": [],
        },
    )

    # Blank keys should now raise ValueError
    with pytest.raises(ValueError, match="Seed key cannot be empty"):
        lst.add_seed({"key": ""})


def test_list_add_seed_with_blank_annotated_seed():
    """Test that List.add_seed rejects AnnotatedSeedDict with blank keys.

    Tests that AnnotatedSeedDict (which has 'thing' and 'notes' keys)
    with blank keys are also properly rejected.
    """
    # Create a mock list with seeds
    lst = List(
        None,
        "/people/test/lists/OL1L",
        {
            "key": "/people/test/lists/OL1L",
            "type": {"key": "/type/list"},
            "name": "Test List",
            "seeds": [],
        },
    )

    # AnnotatedSeedDict with blank key should raise ValueError
    with pytest.raises(ValueError, match="Seed key cannot be empty"):
        lst.add_seed({"thing": {"key": ""}, "notes": "some notes"})


class TestListCard:
    """`List.card` only reads plain attributes, so a stand-in for the list is enough."""

    @staticmethod
    def _preview(viewer=None, *, owner_name="Jane", description="", cover=None):
        owner = SimpleNamespace(key="/people/jane", name=owner_name)
        lst = SimpleNamespace(
            key="/people/jane/lists/OL1L",
            name="Dogs",
            seeds=[object(), object()],
            last_modified=datetime(2020, 1, 15),
            description=description,
            get_owner=lambda: owner,
            get_cover=lambda: cover,
            get_default_cover=lambda: None,
        )
        return List.card(cast(List, lst), viewer)

    def test_values(self):
        preview = self._preview("/people/bob", description="**bold**")
        assert preview.key == "/people/jane/lists/OL1L"
        assert preview.name == "Dogs"
        assert preview.cover_url == "/static/images/icons/avatar_book-sm.png"
        assert (preview.owner_key, preview.owner_name, preview.is_owner) == ("/people/jane", "Jane", False)
        assert preview.item_count == 2
        assert preview.modified == "January 15, 2020"
        assert "<strong>bold</strong>" in preview.description_html

    def test_cover_url_comes_from_the_cover(self):
        cover = SimpleNamespace(url=lambda size: f"/covers/{size}.jpg")
        assert self._preview(cover=cover).cover_url == "/covers/M.jpg"

    def test_viewer_is_the_owner(self):
        assert self._preview("/people/jane").is_owner
        assert not self._preview(None).is_owner

    def test_owner_name_is_truncated_for_the_byline(self):
        assert self._preview(owner_name="N" * 60).owner_name == "N" * 40 + "..."

    def test_no_description(self):
        assert self._preview().description_html == ""
