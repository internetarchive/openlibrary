from openlibrary.accounts import model, InternetArchiveAccount
from requests.models import Response


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
        assert xauth('create', s3_key='_', s3_secret='_') == {'code': 500, 'error':
                                                              'Internal Server Error'}

    def test_xauth_http_error_with_json(self, monkeypatch):
        xauth = InternetArchiveAccount.xauth
        resp = Response()
        resp.status_code = 400
        resp._content = b'{"error": "Unknown Parameter Blah"}'
        monkeypatch.setattr(model.requests, 'post', lambda url, **kwargs: resp)
        assert xauth('create', s3_key='_', s3_secret='_') == {"error":
                                                              "Unknown Parameter Blah"}
