"""
Capture some of the unintuitive aspects of Storage, Things, and Works
"""

import web

import openlibrary.core.lists.model as list_model
from infogami.infobase import client
from openlibrary.mocks.mock_infobase import MockSite

from .. import models


class TestModels:
    def setup_method(self, method):
        web.ctx.site = MockSite()

    def test_setup(self):
        expected_things = {
            '/type/edition': models.Edition,
            '/type/author': models.Author,
            '/type/work': models.Work,
            '/type/subject': models.Subject,
            '/type/place': models.SubjectPlace,
            '/type/person': models.SubjectPerson,
            '/type/user': models.User,
            '/type/list': list_model.List,
        }
        expected_changesets = {
            None: models.Changeset,
            'merge-authors': models.MergeAuthors,
            'undo': models.Undo,
            'add-book': models.AddBookChangeset,
            'lists': list_model.ListChangeset,
            'new-account': models.NewAccountChangeset,
        }
        models.setup()
        for key, value in expected_things.items():
            assert client._thing_class_registry[key] == value
        for key, value in expected_changesets.items():
            assert client._changeset_class_register[key] == value

    def test_work_without_data(self):
        work = models.Work(web.ctx.site, '/works/OL42679M')
        assert repr(work) == str(work) == "<Work: '/works/OL42679M'>"
        assert isinstance(work, client.Thing)
        assert isinstance(work, models.Work)
        assert work._site == web.ctx.site
        assert work.key == '/works/OL42679M'
        assert work._data is None
        # assert isinstance(work.data, client.Nothing)  # Fails!
        # assert work.data is None  # Fails!
        # assert not work.hasattr('data')  # Fails!
        assert work._revision is None
        # assert work.revision is None  # Fails!
        # assert not work.revision('data')  # Fails!

    def test_work_with_data(self):
        work = models.Work(web.ctx.site, '/works/OL42679M', web.Storage())
        assert repr(work) == str(work) == "<Work: '/works/OL42679M'>"
        assert isinstance(work, client.Thing)
        assert isinstance(work, models.Work)
        assert work._site == web.ctx.site
        assert work.key == '/works/OL42679M'
        assert isinstance(work._data, web.Storage)
        assert isinstance(work._data, dict)
        assert hasattr(work, 'data')
        assert isinstance(work.data, client.Nothing)

        assert hasattr(work, 'any_attribute')  # hasattr() is True for all keys!
        assert isinstance(work.any_attribute, client.Nothing)
        assert repr(work.any_attribute) == '<Nothing>'
        assert str(work.any_attribute) == ''

        work.new_attribute = 'new_attribute'
        assert isinstance(work.data, client.Nothing)  # Still Nothing
        assert work.new_attribute == 'new_attribute'
        assert work['new_attribute'] == 'new_attribute'
        assert work.get('new_attribute') == 'new_attribute'

        assert not work.hasattr('new_attribute')
        assert work._data == {'new_attribute': 'new_attribute'}
        assert repr(work.data) == '<Nothing>'
        assert str(work.data) == ''

        assert callable(work.get_sorted_editions)  # Issue #3633
        assert work.get_sorted_editions() == []

    def test_user_settings(self):
        user = models.User(web.ctx.site, 'user')
        assert user.get_safe_mode() == ""
        user.save_preferences({'safe_mode': 'yes'})
        assert user.get_safe_mode() == 'yes'
        user.save_preferences({'safe_mode': "no"})
        assert user.get_safe_mode() == "no"
        user.save_preferences({'safe_mode': 'yes'})
        assert user.get_safe_mode() == 'yes'
