from web import storage
from openlibrary.core import sponsorships
from openlibrary.core.sponsorships import do_we_want_it


class TestSponsorship:
    def test_get_sponsored_editions(self, monkeypatch):
        user = storage(key='/person/mekBot')

        monkeypatch.setattr(
            sponsorships, 'get_internet_archive_id', lambda user_key: '@username'
        )
        assert sponsorships.get_internet_archive_id(user) == '@username'

        class RequestMock(dict):
            def __init__(self, *arg):
                super().__init__(*arg)

            def json(self):
                return self

        monkeypatch.setattr(
            sponsorships.requests,
            'get',
            lambda url, **kwargs: RequestMock({'response': {'docs': []}}),
        )

        assert sponsorships.get_sponsored_editions(user) == []

    def test_get_sponsored_editions_civi(self, monkeypatch):
        user = storage(key='/person/mekBot')

        monkeypatch.setattr(
            sponsorships, 'get_internet_archive_id', lambda user_key: '@username'
        )
        assert sponsorships.get_internet_archive_id(user) == '@username'
        monkeypatch.setattr(
            sponsorships, 'get_contact_id_by_username', lambda archive_id: None
        )
        assert sponsorships.get_contact_id_by_username('@username') is None
        assert sponsorships.get_sponsored_editions_civi(user) == []

        monkeypatch.setattr(
            sponsorships, 'get_contact_id_by_username', lambda archive_id: '123'
        )
        assert sponsorships.get_contact_id_by_username('@username') == '123'
        monkeypatch.setattr(
            sponsorships,
            'get_sponsorships_by_contact_id',
            lambda contact_id: ['fake_data'],
        )
        assert sponsorships.get_sponsored_editions_civi(user) == ['fake_data']

    def test_do_we_want_it(self, monkeypatch, mock_site):
        isbn = '0123456789'

        # Simulating exception / API call failure ...
        monkeypatch.setattr(
            sponsorships.requests, 'get', lambda url, **kwargs: {'invalid': 'json'}
        )
        dwwi, matches = do_we_want_it(isbn)
        assert dwwi is False
        assert matches == []

        monkeypatch.setattr(sponsorships.requests, 'get', lambda url, **kwargs: None)
        dwwi, matches = do_we_want_it(isbn)
        assert dwwi is False
        assert matches == []

        # We need a copy ...
        r = storage({'json': lambda: {"response": 1}})
        monkeypatch.setattr(sponsorships.requests, 'get', lambda url, **kwargs: r)
        dwwi, matches = do_we_want_it(isbn)
        assert dwwi is True
        assert matches == []
