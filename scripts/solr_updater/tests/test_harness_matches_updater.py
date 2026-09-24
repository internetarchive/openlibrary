"""The e2e harness carries its own copy of the updater logic. Pin them together.

`scripts/test_harness_e2e.py` reimplements `collect_dirty_identifiers`,
`is_releasing_event` and `build_solr_updates` inline, on purpose: it needs only
`requests` and a bare Solr container, so a reviewer can run the whole cycle
without OL config or IA credentials. Importing the real module would pull in
infogami and `openlibrary.core.lending` and destroy that property.

The cost is drift, and the drift is not hypothetical -- it happened. The real
updater stopped joining against the availability service and the harness's copy
went on doing it, so the harness kept "passing" while demonstrating a design the
code no longer had. Nothing caught that, because nothing compared them.

This does. It runs both implementations over the same inputs and fails on any
disagreement, which is cheap because the harness's helpers are pure functions
that touch no Solr.
"""

import importlib.util
import inspect
import pathlib

import pytest

from scripts.solr_updater.loan_availability_updater import (
    build_solr_updates,
    collect_dirty_identifiers,
    is_releasing_event,
)

HARNESS_PATH = pathlib.Path(__file__).parents[2] / "test_harness_e2e.py"


@pytest.fixture(scope="module")
def harness():
    """Import the harness by path. It is a script, not a package member."""
    spec = importlib.util.spec_from_file_location("harness_e2e", HARNESS_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ID_TO_EDITION = {"bookabc": {"key": "/books/OL1M", "root": "/works/OL1W"}}

CASES = [
    ("borrow", '{"until": "2026-05-15 10:00:00"}'),
    ("browse", '{"until": "2026-05-02 12:00:00"}'),
    ("renew_borrow", "{}"),
    ("return", "{}"),
    ("expire", "{}"),
    ("expire_browse", "{}"),
    ("expire_borrow", "{}"),
    ("cancel_hold", "{}"),
    ("some_future_verb", "{}"),
    ("", "{}"),
]


@pytest.mark.parametrize(("event_type", "extra"), CASES)
def test_releasing_classification_agrees(harness, event_type, extra):
    assert harness._is_releasing_event(event_type) == is_releasing_event(event_type), event_type


@pytest.mark.parametrize(("event_type", "extra"), CASES)
def test_updates_agree(harness, event_type, extra):
    """Compared as whole documents, not just the availability value: a harness
    that wrote the right flag with the wrong `_root_` would still mislead a
    reviewer about what the updater sends to Solr."""
    rows = [{"identifier": "bookabc", "uid": 100, "event_type": event_type, "extra": extra}]

    mine = build_solr_updates(collect_dirty_identifiers(rows), ID_TO_EDITION)
    theirs = harness._build_updates(harness._collect_dirty(rows), ID_TO_EDITION)

    assert theirs == mine, f"harness and updater disagree for event_type={event_type!r}"


def test_collect_dirty_agrees_on_collapsing_a_batch(harness):
    """Both must collapse to the highest uid per identifier and keep its event
    type -- the harness losing the event type is exactly how it would silently
    revert to treating every event the same way."""
    rows = [
        {"identifier": "bookabc", "uid": 100, "event_type": "borrow", "extra": '{"until": "2026-05-15 10:00:00"}'},
        {"identifier": "bookabc", "uid": 200, "event_type": "return", "extra": "{}"},
    ]
    assert harness._collect_dirty(rows) == collect_dirty_identifiers(rows)


def test_the_harness_does_not_consult_availability(harness):
    """The follower's defining property. If the harness's copy regained an
    availability argument, its signature would stop matching and a reviewer
    would be shown a join the updater does not perform."""
    assert list(inspect.signature(harness._build_updates).parameters) == list(inspect.signature(build_solr_updates).parameters)
