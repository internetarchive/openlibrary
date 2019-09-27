import pytest
import web

from openlibrary.catalog.add_book.merge import try_merge
from openlibrary.core.models import Edition
from openlibrary.mocks.mock_infobase import MockSite

@pytest.mark.skip("This should be tested, but tidy up deprecated methods first.")
def test_try_merge():
    web.ctx.site = MockSite()
    bpl = {'authors': [{'birth_date': u'1897',
                      'db_name': u'Green, Constance McLaughlin 1897-',
                      'entity_type': 'person',
                      'name': u'Green, Constance McLaughlin',
                      'personal_name': u'Green, Constance McLaughlin'}],
         'full_title': u'Eli Whitney and the birth of American technology',
         'isbn': [u'188674632X'],
         'normalized_title': u'eli whitney and the birth of american technology',
         'number_of_pages': 215,
         'publish_date': '1956',
         'publishers': [u'HarperCollins', u'[distributed by Talman Pub.]'],
         'short_title': u'eli whitney and the birth',
         'source_record_loc': 'bpl101.mrc:0:1226',
         'titles': [u'Eli Whitney and the birth of American technology',
                    u'eli whitney and the birth of american technology']}
    # This existing needs to be an Edition Thing object.
    existing = {'authors': [{'birth_date': u'1897',
                     'db_name': u'Green, Constance McLaughlin 1897-',
                     'entity_type': 'person',
                     'name': u'Green, Constance McLaughlin',
                     'personal_name': u'Green, Constance McLaughlin'}],
        'full_title': u'Eli Whitney and the birth of American technology.',
        'isbn': [],
        'normalized_title': u'eli whitney and the birth of american technology',
        'number_of_pages': 215,
        'publish_date': '1956',
        'publishers': ['Little, Brown'],
        'short_title': u'eli whitney and the birth',
        'source_record_loc': 'marc_records_scriblio_net/part04.dat:119539872:591',
        'title': 'Eli Whitney and the birth of American technology.',
        'type': {'key': '/type/edition'},
        'key': '/books/OL1M'}

    web.ctx.site.save_many([existing])
    ed = web.ctx.site.get('/books/OL1M')
    assert try_merge(bpl, '/books/OL1M', ed) is True

