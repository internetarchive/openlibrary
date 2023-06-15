from openlibrary.accounts import model, InternetArchiveAccount, OpenLibraryAccount
from requests.models import Response
import unittest
from unittest import mock


def test_verify_hash():
    secret_key = b"aqXwLJVOcV"
    hash = model.generate_hash(secret_key, b"foo")
    assert model.verify_hash(secret_key, b"foo", hash)


class TestInternetArchiveAccount:
    def test_xauth_http_error_without_json(self, monkeypatch):
        xauth = InternetArchiveAccount.xauth
        resp = Response()
        resp.status_code = 500
        resp._content = b'Internal Server Error'
        monkeypatch.setattr(model.requests, 'post', lambda url, **kwargs: resp)
        assert xauth('create', s3_key='_', s3_secret='_') == {
            'code': 500,
            'error': 'Internal Server Error',
        }

    def test_xauth_http_error_with_json(self, monkeypatch):
        xauth = InternetArchiveAccount.xauth
        resp = Response()
        resp.status_code = 400
        resp._content = b'{"error": "Unknown Parameter Blah"}'
        monkeypatch.setattr(model.requests, 'post', lambda url, **kwargs: resp)
        assert xauth('create', s3_key='_', s3_secret='_') == {
            "error": "Unknown Parameter Blah"
        }


class OpenLibraryAccountTests(unittest.TestCase):
    @mock.patch("openlibrary.accounts.model.web")
    def test_get(self, mock_web):
        test = True

        email = "test@example.com"
        account = OpenLibraryAccount.get_by_email(email)
        self.assertIsNone(account)

        test_account = OpenLibraryAccount.create(
            username="test",
            email=email,
            password="password",
            displayname="Test User",
            verified=True,
            retries=0,
            test=True,
        )

        mock_site = mock_web.ctx.site
        mock_site.store.get.return_value = {
            "username": "test",
            "itemname": "@test",
            "email": "test@example.com",
            "displayname": "Test User",
            "test": True,
        }

        key = "test/test"
        tusername = test_account.username

        retrieved_account = OpenLibraryAccount.get(email=email, test=test)
        self.assertEqual(retrieved_account, test_account)

        mock_site = mock_web.ctx.site
        mock_site.store.values.return_value = [
            {
                "username": "test",
                "itemname": "@test",
                "email": "test@example.com",
                "displayname": "Test User",
                "test": True,
                "type": "account",
                "name": "internetarchive_itemname",
                "value": tusername,
            }
        ]

        retrieved_account = OpenLibraryAccount.get(link=tusername, test=test)
        self.assertIsNotNone(retrieved_account)
        rusername = self.get_username(retrieved_account)
        self.assertEqual(rusername, tusername)

        mock_site.store.values.return_value[0]["name"] = "username"

        retrieved_account = OpenLibraryAccount.get(username=tusername, test=test)
        self.assertIsNotNone(retrieved_account)
        rusername = self.get_username(retrieved_account)
        self.assertEqual(rusername, tusername)

        key = f'test/{rusername}'

        retrieved_account = OpenLibraryAccount.get(key=key, test=test)
        self.assertIsNotNone(retrieved_account)
        rusername = self.get_username(retrieved_account)
        self.assertEqual(rusername, tusername)

    @staticmethod
    def get_username(account):
        return account.value if account is not None else None
