import ol
import web

b = ol.app.browser()
b.debug = True

def test_home():
    b.open('/')
    b.status == 200

def test_write():
    b.open('/sandbox/test?m=edit')
    b.select_form(name="edit")
    b['title'] = 'Foo'
    b['body'] = 'Bar'
    b.submit()
    assert b.path == '/sandbox/test'

    b.open('/')
    assert '/sandbox/test' in b.data

def test_login():
    # try with bad account
    b.open('/account/login')   
    b.select_form(name="login")
    b['username'] = 'baduser'
    b['password'] = 'badpassword'

    try:
        b.submit() 
    except web.BrowserError, e:
        assert str(e) == 'Invalid username or password'
    else:
        assert False, 'Expected exception'

    # follow register link
    b.follow_link(text='create a new account')
    assert b.path == '/account/register'

    b.select_form('register')
    b['username'] = 'joe'
    b['displayname'] = 'Joe'
    b['password'] = 'secret'
    b['password2'] = 'secret'
    b['email'] = 'joe@example.com'
    b.submit()
    assert b.path == '/'

def test_notfound():
    try:
        b.open('/notthere')
    except web.BrowserError:
        assert b.status == 404

def test_bookreader():
    b.open('/details/openlibrary')

