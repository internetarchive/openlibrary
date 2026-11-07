from types import SimpleNamespace

import web

from openlibrary.core import tags


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
