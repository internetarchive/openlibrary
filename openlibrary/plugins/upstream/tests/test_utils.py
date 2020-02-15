# -*- coding: utf-8 -*-
from openlibrary.plugins.upstream import utils

def test_url_quote():
    assert utils.url_quote('https://foo bar') == 'https%3A%2F%2Ffoo+bar'
    assert utils.url_quote('abc') == 'abc'
    assert utils.url_quote('Kabitā') == 'Kabit%C4%81'
    assert utils.url_quote(u'Kabit\u0101') == 'Kabit%C4%81'

def test_entity_decode():
    assert utils.entity_decode('&gt;foo') == '>foo'
    assert utils.entity_decode('<h1>') == '<h1>'

def test_set_share_links():
    class TestContext(object):
        def __init__(self):
            self.share_links = None
    test_context = TestContext()
    utils.set_share_links(url='https://foo.com', title="bar", view_context=test_context)
    assert test_context.share_links == [
        {'text': 'Facebook', 'url': 'https://www.facebook.com/sharer/sharer.php?u=https%3A%2F%2Ffoo.com'},
        {'text': 'Twitter', 'url': 'https://twitter.com/intent/tweet?url=https%3A%2F%2Ffoo.com&via=openlibrary&text=Check+this+out%3A+bar'},
        {'text': 'Pinterest', 'url': 'https://pinterest.com/pin/create/link/?url=https%3A%2F%2Ffoo.com&description=Check+this+out%3A+bar'}
    ]

def test_set_share_links_unicode():
    # example work that has a unicode title: https://openlibrary.org/works/OL14930766W/Kabit%C4%81
    class TestContext(object):
        def __init__(self):
            self.share_links = None
    test_context = TestContext()
    utils.set_share_links(url=u'https://foo.\xe9', title=u'b\u0101', view_context=test_context)
    assert test_context.share_links == [
        {'text': 'Facebook', 'url': 'https://www.facebook.com/sharer/sharer.php?u=https%3A%2F%2Ffoo.%C3%A9'},
        {'text': 'Twitter', 'url': 'https://twitter.com/intent/tweet?url=https%3A%2F%2Ffoo.%C3%A9&via=openlibrary&text=Check+this+out%3A+b%C4%81'},
        {'text': 'Pinterest', 'url': 'https://pinterest.com/pin/create/link/?url=https%3A%2F%2Ffoo.%C3%A9&description=Check+this+out%3A+b%C4%81'}
    ]

def test_item_image():
    assert utils.item_image('//foo') == 'https://foo'
    assert utils.item_image(None, 'bar') == 'bar'
    assert utils.item_image(None) == None
