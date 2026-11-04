from types import SimpleNamespace

import pytest
import web

from openlibrary.core import tags


class FakeUser:
    def __init__(self, groups=()):
        self.groups = set(groups)

    def is_admin(self):
        return "/usergroup/admin" in self.groups

    def is_usergroup_member(self, group):
        return group in self.groups


def test_tags_are_editable_by_admins_and_the_beta_group_only():
    assert not tags.can_edit_tags(None)
    assert not tags.can_edit_tags(FakeUser(["/usergroup/librarians"]))
    assert tags.can_edit_tags(FakeUser(["/usergroup/admin"]))
    assert tags.can_edit_tags(FakeUser([tags.TAGS_BETA_GROUP]))


def test_a_tag_reference_reads_the_same_in_every_stored_shape():
    assert tags.tag_key("/tags/OL1T") == "/tags/OL1T"
    assert tags.tag_key({"key": "/tags/OL1T"}) == "/tags/OL1T"
    assert tags.tag_key(web.storage(key="/tags/OL1T")) == "/tags/OL1T"
    assert tags.tag_key(None) is None
    assert tags.tag_key("") is None


def test_work_tag_keys_flattens_one_or_many():
    work = {"literary_forms": [{"key": "/tags/OL1T"}], "subgenres": {"key": "/tags/OL4T"}, "genres": ["/tags/OL2T", {"key": "/tags/OL3T"}]}
    assert tags.work_tag_keys(work, "literary_forms") == ["/tags/OL1T"]
    assert tags.work_tag_keys(work, "genres") == ["/tags/OL2T", "/tags/OL3T"]
    assert tags.work_tag_keys(work, "subgenres") == ["/tags/OL4T"]
    assert tags.work_tag_keys(work, "audiences") == []


def test_work_tags_keeps_field_order_and_skips_unknown_tags(monkeypatch):
    found = {
        "/tags/OL1T": web.storage(key="/tags/OL1T", name="Fiction", tag_type="literary_form"),
        "/tags/OL2T": web.storage(key="/tags/OL2T", name="Crime", tag_type="genres"),
    }
    site = SimpleNamespace(get_many=lambda keys: [found[k] for k in keys if k in found])
    monkeypatch.setattr(tags, "site", SimpleNamespace(get=lambda: site))
    work = {"genres": ["/tags/OL2T", "/tags/OL9T"], "literary_forms": ["/tags/OL1T"]}
    assert [t["name"] for t in tags.work_tags(work)] == ["Fiction", "Crime"]
    assert tags.work_tags({}) == []


@pytest.fixture(autouse=True)
def fresh_tag_cache():
    tags.clear_cache()
    yield
    tags.clear_cache()


def fake_site(found: dict, by_type: dict):
    return SimpleNamespace(
        things=lambda q: by_type.get(q["tag_type"], []),
        get_many=lambda keys: [found[k] for k in keys if k in found],
    )


def test_a_field_s_tags_come_from_every_tag_type_it_has_been_called(monkeypatch):
    found = {
        "/tags/OL1T": web.storage(key="/tags/OL1T", name="Romance", tag_type="genres", tag_description="Love"),
        "/tags/OL2T": web.storage(key="/tags/OL2T", name="Crime", tag_type="genre"),
        "/tags/OL3T": web.storage(key="/tags/OL3T", name="", tag_type="genre"),
    }
    site = fake_site(found, {"genres": ["/tags/OL1T"], "genre": ["/tags/OL2T", "/tags/OL3T"]})
    monkeypatch.setattr(tags, "site", SimpleNamespace(get=lambda: site))
    assert [t.name for t in tags.get_tags_of_type("genres")] == ["Crime", "Romance"]
    assert tags.find_tag("genres", "/tags/OL1T").tag_description == "Love"
    assert tags.find_tag("genres", "/tags/OL3T") is None
    assert [o["value"] for o in tags.tag_options("genres")] == ["/tags/OL2T", "/tags/OL1T"]


def test_the_literary_form_is_read_by_name(monkeypatch):
    found = {
        "/tags/OL1T": web.storage(key="/tags/OL1T", name="Fiction", tag_type="literary_form"),
        "/tags/OL2T": web.storage(key="/tags/OL2T", name="Nonfiction", tag_type="literary_form"),
    }
    site = fake_site(found, {"literary_form": ["/tags/OL1T", "/tags/OL2T"]})
    monkeypatch.setattr(tags, "site", SimpleNamespace(get=lambda: site))
    assert tags.tag_key_named("literary_forms", "fiction") == "/tags/OL1T"
    assert tags.tag_key_named("literary_forms", "poetry") is None
    assert tags.literary_form_of({"literary_forms": [{"key": "/tags/OL2T"}]}) == "nonfiction"
    assert tags.is_nonfiction({"literary_forms": ["/tags/OL2T"]})
    assert not tags.is_nonfiction({"literary_forms": ["/tags/OL1T"]})
    assert not tags.is_nonfiction({})
    # A key the vocabulary no longer has reads as unset.
    assert tags.literary_form_of({"literary_forms": ["/tags/OL9T"]}) == ""
    assert tags.work_tag_names({"literary_forms": ["/tags/OL1T"]}, "literary_forms") == ["Fiction"]


def test_the_subjects_name_genres_by_slug_as_whole_words(monkeypatch):
    found = {
        "/tags/OL1T": web.storage(key="/tags/OL1T", name="Horror", tag_type="genre", slugs=["horror", "ghost_stories"]),
        "/tags/OL2T": web.storage(key="/tags/OL2T", name="Historical", tag_type="genre"),
        "/tags/OL3T": web.storage(key="/tags/OL3T", name="Science Fiction", tag_type="genre"),
        "/tags/OL4T": web.storage(key="/tags/OL4T", name="Thriller", tag_type="genre"),
    }
    site = fake_site(found, {"genre": list(found)})
    monkeypatch.setattr(tags, "site", SimpleNamespace(get=lambda: site))
    # A tag without slugs matches on its name.
    assert tags.find_tag("genres", "/tags/OL2T").slugs == ["historical"]
    subjects = ["Horror stories", "Fiction, science fiction, apocalyptic", "History", "Thrillers", "Ghost stories", "Children's fiction"]
    assert tags.subject_matches("genres", subjects) == {
        "/tags/OL1T": ["Horror stories", "Ghost stories"],
        "/tags/OL3T": ["Fiction, science fiction, apocalyptic"],
        "/tags/OL4T": ["Thrillers"],
    }
    assert tags.subject_matches("genres", []) == {}


def test_the_tag_list_is_read_once_per_window(monkeypatch):
    reads = []
    site = SimpleNamespace(things=lambda q: reads.append(q) or [], get_many=lambda keys: [])
    monkeypatch.setattr(tags, "site", SimpleNamespace(get=lambda: site))
    tags.get_tags_of_type("genres")
    tags.get_tags_of_type("genres")
    assert len(reads) == 2  # one per tag type the field has had, then cached
