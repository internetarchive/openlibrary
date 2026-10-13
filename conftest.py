"""Repo-wide pytest configuration.

Tests must behave the same in the dev container as in CI, so the deployment
flags compose sets are dropped before any test module is imported (some read
them at import time). A test that needs dev-mode behaviour opts in with the
``local_dev`` fixture.
"""

import os

import pytest

os.environ.pop("LOCAL_DEV", None)
os.environ.pop("OL_DEPLOYMENT_NAME", None)


@pytest.fixture
def local_dev(monkeypatch):
    """Run the test as if LOCAL_DEV=true."""
    from openlibrary.core.env import get_ol_env  # noqa: PLC0415

    monkeypatch.setattr(get_ol_env(), "LOCAL_DEV", True)
