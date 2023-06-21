from openlibrary.plugins.books import readlinks
import pytest

import web


class TestReadProcessor:
    def test_get_item_status_lending_library_true(self, mock_site):
        collections = ['lendinglibrary']
        subjects = ['Lending library']

        status = readlinks.ReadProcessor.get_item_status(
            self, 'ekey', 'iaid', collections, subjects
        )
        assert status == 'lendable'

    def test_get_item_status_lending_library_false(self):
        collections = ['lendinglibrary']
        subjects = ['Some other subject']

        status = readlinks.ReadProcessor.get_item_status(
            self, 'ekey', 'iaid', collections, subjects
        )
        assert status == 'restricted'

    def test_get_item_status_in_library_true(self):
        collections = ['inlibrary']
        subjects = ['In library']
        readlinks.ReadProcessor.__init__(self, options={})

        status = readlinks.ReadProcessor.get_item_status(
            self, 'ekey', 'iaid', collections, subjects
        )
        assert status == 'restricted'

    def test_get_item_status_in_library_debug_true(self):
        collections = ['inlibrary']
        subjects = ['In library']
        readlinks.ReadProcessor.__init__(self, options={'debug_items': True})

        status = readlinks.ReadProcessor.get_item_status(
            self, 'ekey', 'iaid', collections, subjects
        )
        assert status == 'restricted - not inlib'

    def test_get_item_status_in_library_show_true(self, mock_site):
        collections = ['inlibrary']
        subjects = ['In library']
        readlinks.ReadProcessor.__init__(self, options={'show_inlibrary': True})

        status = readlinks.ReadProcessor.get_item_status(
            self, 'ekey', 'iaid', collections, subjects
        )
        assert status == 'lendable'

    def test_get_item_status_print_disabled_true(self):
        collections = ['printdisabled']
        subjects = []

        status = readlinks.ReadProcessor.get_item_status(
            self, 'ekey', 'iaid', collections, subjects
        )
        assert status == 'restricted'

    def test_get_item_status_print_disabled_false(self):
        collections = ['some other collection']
        subjects = []

        status = readlinks.ReadProcessor.get_item_status(
            self, 'ekey', 'iaid', collections, subjects
        )
        assert status == 'full access'

    def test_get_item_status_checked_out_true(self, monkeypatch, mock_site):
        collections = ['lendinglibrary']
        subjects = ['Lending library']
        readlinks.ReadProcessor.__init__(self, options={})

        monkeypatch.setattr(
            web.ctx.site.store, 'get', lambda _, __: {'borrowed': 'true'}
        )

        status = readlinks.ReadProcessor.get_item_status(
            self, 'ekey', 'iaid', collections, subjects
        )
        assert status == 'checked out'

    def test_get_item_status_checked_out_false(self, monkeypatch, mock_site):
        collections = ['lendinglibrary']
        subjects = ['Lending library']
        readlinks.ReadProcessor.__init__(self, options={})

        monkeypatch.setattr(
            web.ctx.site.store, 'get', lambda _, __: {'borrowed': 'false'}
        )

        status = readlinks.ReadProcessor.get_item_status(
            self, 'ekey', 'iaid', collections, subjects
        )
        assert status == 'lendable'
