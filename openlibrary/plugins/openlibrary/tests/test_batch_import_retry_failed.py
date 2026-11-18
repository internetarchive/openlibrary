"""The flash message after re-queueing a batch's failed items uses a real plural."""

from unittest.mock import MagicMock, patch

import pytest

from openlibrary.plugins.openlibrary import code
from openlibrary.plugins.openlibrary.code import BatchImportRetryFailed


@pytest.mark.parametrize(
    ("count", "message"),
    [
        (1, "Re-queued 1 failed item."),
        (3, "Re-queued 3 failed items."),
        (0, "Re-queued 0 failed items."),
    ],
)
def test_retry_failed_flash_message_is_pluralised(request_context_fixture, count, message):
    # ungettext needs a language; real requests default to "en" (request_context.py).
    request_context_fixture(lang="en")
    batch = MagicMock()
    batch.retry_failed.return_value = count
    flash = MagicMock()
    with (
        patch.object(code, "_require_admin", lambda: None),
        patch.object(code, "db", MagicMock(select=MagicMock(return_value=[{"id": 5}]))),
        patch.object(code, "Batch", MagicMock(return_value=batch)),
        patch.object(code, "add_flash_message", flash),
        patch.object(code.web, "seeother", lambda url: ("seeother", url)),
    ):
        result = BatchImportRetryFailed().POST("5")

    flash.assert_called_once_with("success", message)
    assert result == ("seeother", "/import/batch/5")
