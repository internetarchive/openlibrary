import datetime

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from openlibrary.coverstore_fastapi import app as app_module


@pytest.fixture
def client():
    # follow_redirects=False so 302/303 responses can be asserted directly.
    return TestClient(app_module.app, follow_redirects=False)


def make_request(headers: dict[str, str]):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/b/id/1.jpg",
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }
    return Request(scope)


def sample_row(created: datetime.datetime) -> dict:
    """A cover row shaped like the DB column order."""
    return {
        "id": 55,
        "category_id": 1,
        "olid": "OL1M",
        "filename": "2026/01/01/OL1M-abc.jpg",
        "filename_s": "2026/01/01/OL1M-abc-S.jpg",
        "filename_m": "2026/01/01/OL1M-abc-M.jpg",
        "filename_l": "2026/01/01/OL1M-abc-L.jpg",
        "author": None,
        "ip": None,
        "source_url": None,
        "source": None,
        "isbn": None,
        "width": 10,
        "height": 20,
        "failed": None,
        "archived": False,
        "uploaded": None,
        "deleted": False,
        "created": created,
        "last_modified": created,
    }


@pytest.fixture
def row():
    return sample_row(datetime.datetime(2026, 1, 2, 3, 4, 5, 678910))
