"""Tests for openlibrary.plugins.upstream.tag_dashboard."""

import web

from openlibrary.plugins.upstream.tag_dashboard import (
    FLAG_KINDS,
    build_tag_dashboard,
)


def make_tag(key: str, name: str, **fields) -> web.storage:
    """A tag with every field the dashboard reads, unless overridden."""
    tag = web.storage(
        key=key,
        name=name,
        tag_type="genres",
        tag_description="A description",
        slugs=[name.casefold().replace(" ", "_")],
    )
    tag.update(fields)
    return tag


def test_groups_by_tag_type_with_counts():
    dashboard = build_tag_dashboard(
        [
            make_tag("/tags/OL1T", "Horror"),
            make_tag("/tags/OL2T", "Romance"),
            make_tag("/tags/OL3T", "Cooking", tag_type="content_formats"),
        ]
    )

    assert dashboard.total == 3
    assert [(group.tag_type, group.count) for group in dashboard.groups] == [
        ("genres", 2),
        ("content_formats", 1),
    ]


def test_group_order_is_by_size_then_name():
    dashboard = build_tag_dashboard(
        [
            make_tag("/tags/OL1T", "A", tag_type="subgenres"),
            make_tag("/tags/OL2T", "B", tag_type="genres"),
            make_tag("/tags/OL3T", "C", tag_type="genres"),
            make_tag("/tags/OL4T", "D", tag_type="audiences"),
            make_tag("/tags/OL5T", "E", tag_type="audiences"),
        ]
    )

    assert [group.tag_type for group in dashboard.groups] == [
        "audiences",
        "genres",
        "subgenres",
    ]


def test_untyped_group_sorts_last():
    dashboard = build_tag_dashboard(
        [
            make_tag("/tags/OL1T", "Untyped", tag_type=None),
            make_tag("/tags/OL2T", "Genres"),
        ]
    )

    assert [group.tag_type for group in dashboard.groups] == ["genres", ""]


def test_tags_within_a_group_are_sorted_by_name_case_insensitively():
    dashboard = build_tag_dashboard(
        [
            make_tag("/tags/OL1T", "zebra"),
            make_tag("/tags/OL2T", "Apple"),
            make_tag("/tags/OL3T", "mango"),
        ]
    )

    (group,) = dashboard.groups
    assert [tag.name for tag in group.tags] == ["Apple", "mango", "zebra"]


def test_singular_type_is_flagged_with_its_canonical_plural():
    dashboard = build_tag_dashboard(
        [
            make_tag("/tags/OL1T", "Horror", tag_type="genre"),
            make_tag("/tags/OL2T", "Romance", tag_type="genres"),
        ]
    )

    assert [tag.key for tag in dashboard.flags["singular_type"]] == ["/tags/OL1T"]
    assert dashboard.canonical_types["genre"] == "genres"


def test_test_tags_are_flagged():
    dashboard = build_tag_dashboard(
        [
            make_tag("/tags/OL1T", "Science Fiction Test"),
            make_tag("/tags/OL2T", "Science Fiction"),
            # Not a test tag: "test" has to be a word of its own.
            make_tag("/tags/OL3T", "Attestation"),
        ]
    )

    assert [tag.key for tag in dashboard.flags["test_tag"]] == ["/tags/OL1T"]


def test_missing_fields_are_flagged():
    dashboard = build_tag_dashboard(
        [
            make_tag("/tags/OL1T", "No type", tag_type=None),
            make_tag("/tags/OL2T", "No description", tag_description=None),
            make_tag("/tags/OL3T", "Blank description", tag_description="   "),
            make_tag("/tags/OL4T", "No slugs", slugs=None),
            make_tag("/tags/OL5T", "No empty list", slugs=[]),
        ]
    )

    assert [tag.key for tag in dashboard.flags["missing_type"]] == ["/tags/OL1T"]
    assert {tag.key for tag in dashboard.flags["missing_description"]} == {"/tags/OL2T", "/tags/OL3T"}
    assert {tag.key for tag in dashboard.flags["missing_slugs"]} == {"/tags/OL4T", "/tags/OL5T"}


def test_every_flag_kind_is_present_in_order():
    dashboard = build_tag_dashboard([])

    assert list(dashboard.flags) == list(FLAG_KINDS)
    assert all(flagged == [] for flagged in dashboard.flags.values())


def test_flags_are_sorted_by_name():
    dashboard = build_tag_dashboard(
        [
            make_tag("/tags/OL1T", "zebra", tag_type=None),
            make_tag("/tags/OL2T", "Apple", tag_type=None),
        ]
    )

    assert [tag.name for tag in dashboard.flags["missing_type"]] == ["Apple", "zebra"]


def test_tags_without_the_optional_keys_are_handled():
    dashboard = build_tag_dashboard([web.storage(key="/tags/OL1T", name="Bare")])

    assert dashboard.total == 1
    assert [group.tag_type for group in dashboard.groups] == [""]
    assert [tag.key for tag in dashboard.flags["missing_description"]] == ["/tags/OL1T"]


def test_truncated_is_passed_through():
    assert build_tag_dashboard([]).truncated is False
    assert build_tag_dashboard([], truncated=True).truncated is True


def test_empty_vocabulary_has_no_groups():
    dashboard = build_tag_dashboard([])

    assert dashboard.total == 0
    assert dashboard.groups == []
