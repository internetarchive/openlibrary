from .. import account
import web
import re

def test_create_list_doc(wildcard):
    key = "account/foo/verify"
    username = "foo"
    email = "foo@example.com"
    
    doc = account.create_link_doc(key, username, email)
    
    assert doc == {
        "_key": key,
        "_rev": None,
        "type": "account-link",
        "username": username,
        "email": email,
        "code": wildcard,
        "created_on": wildcard,
        "expires_on": wildcard
    }
    
def test_verify_hash():
    secret_key = "aqXwLJVOcV"
    hash = account.generate_hash(secret_key, "foo")
    assert account.verify_hash(secret_key, "foo", hash) == True


class TestAccount:
    def signup(self, b, displayname, username, password, email):
        b.open("/account/create")
        b.select_form(name="signup")

        b['displayname'] = 'Foo'
        b['username'] = 'foo'
        b['password'] = 'secret2'
        b['email'] = 'foo@example.com'
        b['agreement'] = ['yes']
        b.submit()

    def test_create(self, ol):
        b = ol.browser
        self.signup(b, displayname="Foo", username="foo", password="secret", email="foo@example.com")
        
        head = b.get_soup().find("div", id="contentHead")
        body = b.get_soup().find("div", id="contentBody")
        
        assert "Hi, foo!" in b.get_text(head)
        assert "sent an email to foo@example.com" in b.get_text(body)
        
        assert ol.sentmail["from_address"] == "Open Library <noreply@openlibrary.org>"
        assert ol.sentmail["to_address"] == "foo@example.com"
        assert ol.sentmail["subject"] == "Welcome to Open Library"
        link = ol.sentmail.extract_links()[0]
        
        assert re.match("^http://0.0.0.0:8080/account/verify/[0-9a-f]{32}$", link)
        
    def test_activate(self, ol):
        b = ol.browser
        
        self.signup(b, displayname="Foo", username="foo", password="secret", email="foo@example.com")
        link = ol.sentmail.extract_links()[0]    
    
        b.open(link)
        
        head = b.get_soup().find("div", id="contentHead")
        body = b.get_soup().find("div", id="contentBody")
        
        assert "Hi, Foo!" in b.get_text(head)        
        assert "Yay! Your email address has been verified." in b.get_text(body)
