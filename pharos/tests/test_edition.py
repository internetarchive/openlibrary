import ol

b = ol.app.browser()

def _test_edit(key, property):
    b.open(key)

    b.follow_link(text='Edit')
    b.select_form(name="edit")
    b[property] += 'XXX test-edit'
    b['_comment'] = 'test_edit comment'
    b.submit(name='_save')

    assert 'XXX test-edit' in b.data

    b.follow_link(text='History')
    assert 'test_edit comment' in b.data

def test_edition():
    _test_edit('/b/OL1M', 'title')

def test_author():
    _test_edit('/a/OL1A', 'name')
    
def test_addbook():
    b.open('/addbook')
    b.select_form(name='edit')
    b['title'] = 'Test Book'

    # authors is readonly because its type is hidden. reset that before modifying.
    b.form.find_control('authors#0.key').readonly = False
    b['authors#0.key'] = '/a/OL1A'
    b.submit()

    assert 'Test Book' in b.data
    assert b.get_links(url_regex='/a/OL1A/')

def test_edit_about():
    _test_edit("/about/tech", "body")

