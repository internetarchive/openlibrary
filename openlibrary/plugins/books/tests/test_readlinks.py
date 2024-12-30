import pytest
import web

from openlibrary.plugins.books import readlinks


@pytest.mark.parametrize(
    ("collections", "subjects", "options", "expected"),
    [
        (['lendinglibrary'], ['Lending library'], {}, 'lendable'),
        (['lendinglibrary'], ['Some other subject'], {}, 'restricted'),
        (['inlibrary'], ['In library'], {}, 'restricted'),
        (
            ['inlibrary'],
            ['In library'],
            {'debug_items': True},
            'restricted - not inlib',
        ),
        (['inlibrary'], ['In library'], {'show_inlibrary': True}, 'lendable'),
        (['printdisabled'], [], {}, 'restricted'),
        (['some other collection'], [], {}, 'full access'),
    ],
)
def test_get_item_status(collections, subjects, options, expected, mock_site):
    read_processor = readlinks.ReadProcessor(options=options)
    status = read_processor.get_item_status('ekey', 'iaid', collections, subjects)
    assert status == expected


@pytest.mark.parametrize(
    ("borrowed", "expected"),
    [
        ('true', 'checked out'),
        ('false', 'lendable'),
    ],
)
def test_get_item_status_monkeypatched(borrowed, expected, monkeypatch, mock_site):
    read_processor = readlinks.ReadProcessor(options={})
    monkeypatch.setattr(web.ctx.site.store, 'get', lambda _, __: {'borrowed': borrowed})
    collections = ['lendinglibrary']
    subjects = ['Lending library']
    status = read_processor.get_item_status('ekey', 'iaid', collections, subjects)
    assert status == expected
