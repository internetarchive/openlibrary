import pytest
from web import storage
from openlibrary.core import sponsorships
from openlibrary.core.sponsorships import get_sponsored_editions, do_we_want_it, qualifies_for_sponsorship

class TestSponsorship:

    def test_get_sponsored_editions(self, monkeypatch):
        user = storage(key='/person/mekBot')

        monkeypatch.setattr(sponsorships, 'get_internet_archive_id', lambda user_key: '@username')
        assert sponsorships.get_internet_archive_id(user) == '@username'
        monkeypatch.setattr(sponsorships, 'get_contact_id_by_username', lambda archive_id: None)
        assert sponsorships.get_contact_id_by_username('@username') is None
        assert sponsorships.get_sponsored_editions(user) == []

        monkeypatch.setattr(sponsorships, 'get_contact_id_by_username', lambda archive_id: '123')
        assert sponsorships.get_contact_id_by_username('@username') == '123'
        monkeypatch.setattr(sponsorships, 'get_sponsorships_by_contact_id', lambda contact_id: ['fake_data'])
        assert sponsorships.get_sponsored_editions(user) == ['fake_data']


    def test_do_we_want_it(self, monkeypatch, mock_site):
        isbn = '0123456789'
        work_id = 'OL1W'
        mock_availability__reject = {
            'OL1W': {
                'status': 'open'
            }
        }
        mock_availability__need = {
            'OL1W': {
                'status': 'error'
            }
        }

        # We already have an edition for this work ...
        monkeypatch.setattr(sponsorships.lending, 'get_work_availability',
                            lambda work_id: mock_availability__reject)
        dwwi, availability = do_we_want_it(isbn, work_id)
        assert dwwi == False
        assert availability == mock_availability__reject

        # Simulating exception / API call failure ...
        monkeypatch.setattr(sponsorships.lending, 'get_work_availability',
                            lambda work_id: mock_availability__need)
        monkeypatch.setattr(sponsorships.requests, 'get', lambda url, **kwargs: {'invalid': 'json'})
        dwwi, matches = do_we_want_it(isbn, work_id)
        assert dwwi == False
        assert matches == []

        # Check archive.org promise items, previous sponsorships ...
        monkeypatch.setattr(sponsorships.lending, 'get_work_availability',
                            lambda work_id: mock_availability__need)
        monkeypatch.setattr(sponsorships.requests, 'get', lambda url, **kwargs: None)
        dwwi, matches = do_we_want_it(isbn, work_id)
        assert dwwi == False
        assert matches == []

        # We need a copy ...
        r = storage({'json': lambda: {"response": 1}})
        monkeypatch.setattr(sponsorships.requests, 'get', lambda url, **kwargs: r)
        dwwi, matches = do_we_want_it(isbn, work_id)
        assert dwwi == True
        assert matches == []

    def qualifies_for_sponsorship(self, monkeypatch):
        # XXX TODO
        work = mock_site.quicksave("/works/OL1W", "/type/work", title="Foo")
