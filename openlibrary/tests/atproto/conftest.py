from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture
def coverstore():
    with patch("openlibrary.atproto.edition_view.get_coverstore_public_url", return_value="https://covers.openlibrary.org"):
        yield
