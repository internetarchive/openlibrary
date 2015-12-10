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

        b['displayname'] = displayname
        b['username'] = username
        b['password'] = password
        b['email'] = email
        b['agreement'] = ['yes']
        b.submit()
        
    def login(self, b, username, password):
        """Attempt login and return True if successful.
        """
        b.open("/account/login")
        b.select_form(name="register") # wrong name
        b["username"] = username
        b["password"] = password
        b.submit()
        
        return b.path == "/"

    def test_create(self, ol):
        b = ol.browser()
        self.signup(b, displayname="Foo", username="foo", password="blackgoat", email="foo@example.com")
                
        assert "Hi, foo!" in b.get_text(id="contentHead")
        assert "sent an email to foo@example.com" in b.get_text(id="contentBody")
        
        assert ol.sentmail["from_address"] == "Open Library <noreply@openlibrary.org>"
        assert ol.sentmail["to_address"] == "foo@example.com"
        assert ol.sentmail["subject"] == "Welcome to Open Library"
        link = ol.sentmail.extract_links()[0]
        
        assert re.match("^http://0.0.0.0:8080/account/verify/[0-9a-f]{32}$", link)
        
    def test_activate(self, ol):
        b = ol.browser()
        
        self.signup(b, displayname="Foo", username="foo", password="secret", email="foo@example.com")
        link = ol.sentmail.extract_links()[0]
        b.open(link)
        
        assert "Hi, Foo!" in b.get_text(id="contentHead")        
        assert "Yay! Your email address has been verified." in b.get_text(id="contentBody")
        
        self.login(b, "foo", "secret")
        
        assert b.path == "/"
        assert "Log out" in b.get_text()        

    def test_forgot_password(self, ol):
        b = ol.browser()
        
        self.signup(b, displayname="Foo", username="foo", password="secret", email="foo@example.com")
        link = ol.sentmail.extract_links()[0]
        b.open(link)
        
        b.open("/account/password/forgot")
        b.select_form(name="register") # why is the form called register?
        b['email'] = "foo@example.com"
        b.submit()
        
        assert "Thanks" in b.get_text(id="contentHead")
        assert "We've sent an email to foo@example.com with instructions" in b.get_text(id="contentBody")
        
        link = ol.sentmail.extract_links()[0]
        assert re.match("^http://0.0.0.0:8080/account/password/reset/[0-9a-f]{32}$", link)
        
        b.open(link)
        assert "Reset Password" in b.get_text(id="contentHead")
        assert "Please enter a new password for your Open Library account" in b.get_text(id="contentBody")
        b.select_form(name="reset")
        b['password'] = "secret2"
        b.submit()
                
        self.login(b, "foo", "secret2")
        assert b.path == "/"
        assert "Log out" in b.get_text()
        
        b.reset()
        self.login(b, "foo", "secret")
        assert b.path == "/account/login"
        assert "That password seems incorrect" in b.get_text()

    def test_change_password(self, ol):
        b = ol.browser()
        self.signup(b, displayname="Foo", username="foo", password="secret", email="foo@example.com")
        link = ol.sentmail.extract_links()[0]
        b.open(link)
        self.login(b, "foo", "secret")
        
        b.open("/account/password")
        b.select_form(name="register")
        b['password'] = "secret"
        b['new_password'] = "more_secret"
        b.submit()
        
        assert b.path == "/account"
        
        b.reset()
        assert self.login(b, "foo", "more_secret") == True

    def test_change_email(self, ol):
        b = ol.browser()
        self.signup(b, displayname="Foo", username="foo", password="secret", email="foo@example.com")

        link = ol.sentmail.extract_links()[0]
        b.open(link)

        self.login(b, "foo", "secret")

        b.open("/account/email")
        
        assert "foo@example.com" in b.data
        
        b.select_form(name="register")
        b['email'] = "foobar@example.com"
        b.submit()
        
        assert "Hi Foo" in b.get_text(id="contentHead")
        assert "We've sent an email to foobar@example.com" in b.get_text(id="contentBody")
        
        link = ol.sentmail.extract_links()[0]
        b.open(link)
        assert "Email verification successful" in b.get_text(id="contentHead")
        
        b.open("/account/email")
        assert "foobar@example.com" in b.data
        