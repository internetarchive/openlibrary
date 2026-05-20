from unittest.mock import MagicMock, patch

import pytest

from openlibrary.core.batch_imports import batch_import

VALID_RECORD = (
    b'{"title": "Test Book", "source_records": ["idb:test123"], "authors": [{"name": "Test Author"}], "publishers": ["Test Publisher"], "publish_date": "2020"}\n'
)


@pytest.fixture
def mock_user():
    user = MagicMock()
    user.get_username.return_value = "testuser"
    return user


@pytest.fixture
def mock_batch():
    batch = MagicMock()
    batch.add_items.return_value = None
    return batch


def test_batch_name_defaults_to_main(mock_user, mock_batch):
    with (
        patch("openlibrary.core.batch_imports.accounts.get_current_user", return_value=mock_user),
        patch("openlibrary.core.batch_imports.Batch.find", return_value=None),
        patch("openlibrary.core.batch_imports.Batch.new", return_value=mock_batch) as mock_new,
    ):
        batch_import(VALID_RECORD, import_status="pending")
        mock_new.assert_called_once_with(name="testuser:main", submitter="testuser")


def test_batch_name_uses_provided_suffix(mock_user, mock_batch):
    with (
        patch("openlibrary.core.batch_imports.accounts.get_current_user", return_value=mock_user),
        patch("openlibrary.core.batch_imports.Batch.find", return_value=None),
        patch("openlibrary.core.batch_imports.Batch.new", return_value=mock_batch) as mock_new,
    ):
        batch_import(VALID_RECORD, import_status="pending", batch_suffix="mybatch")
        mock_new.assert_called_once_with(name="testuser:mybatch", submitter="testuser")


def test_batch_name_strips_whitespace(mock_user, mock_batch):
    with (
        patch("openlibrary.core.batch_imports.accounts.get_current_user", return_value=mock_user),
        patch("openlibrary.core.batch_imports.Batch.find", return_value=None),
        patch("openlibrary.core.batch_imports.Batch.new", return_value=mock_batch) as mock_new,
    ):
        batch_import(VALID_RECORD, import_status="pending", batch_suffix="  mybatch  ")
        mock_new.assert_called_once_with(name="testuser:mybatch", submitter="testuser")


def test_batch_name_empty_string_falls_back_to_main(mock_user, mock_batch):
    with (
        patch("openlibrary.core.batch_imports.accounts.get_current_user", return_value=mock_user),
        patch("openlibrary.core.batch_imports.Batch.find", return_value=None),
        patch("openlibrary.core.batch_imports.Batch.new", return_value=mock_batch) as mock_new,
    ):
        batch_import(VALID_RECORD, import_status="pending", batch_suffix="")
        mock_new.assert_called_once_with(name="testuser:main", submitter="testuser")


def test_batch_name_whitespace_only_falls_back_to_main(mock_user, mock_batch):
    with (
        patch("openlibrary.core.batch_imports.accounts.get_current_user", return_value=mock_user),
        patch("openlibrary.core.batch_imports.Batch.find", return_value=None),
        patch("openlibrary.core.batch_imports.Batch.new", return_value=mock_batch) as mock_new,
    ):
        batch_import(VALID_RECORD, import_status="pending", batch_suffix="   ")
        mock_new.assert_called_once_with(name="testuser:main", submitter="testuser")


def test_raises_when_no_authenticated_user():
    with (
        patch("openlibrary.core.batch_imports.accounts.get_current_user", return_value=None),
        pytest.raises(ValueError, match="authenticated user"),
    ):
        batch_import(VALID_RECORD, import_status="pending")


def test_reuses_existing_batch(mock_user, mock_batch):
    with (
        patch("openlibrary.core.batch_imports.accounts.get_current_user", return_value=mock_user),
        patch("openlibrary.core.batch_imports.Batch.find", return_value=mock_batch) as mock_find,
        patch("openlibrary.core.batch_imports.Batch.new") as mock_new,
    ):
        batch_import(VALID_RECORD, import_status="pending", batch_suffix="existing")
        mock_find.assert_called_once_with("testuser:existing")
        mock_new.assert_not_called()
        mock_batch.add_items.assert_called_once()
