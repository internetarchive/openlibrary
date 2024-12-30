import os
import re
import sys

import pytest
import web

from .. import account


def open_test_data(filename):
    """Returns a file handle to file with specified filename inside test_data directory."""
    root = os.path.dirname(__file__)
    fullpath = os.path.join(root, 'test_data', filename)
    return open(fullpath, mode='rb')


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
        "expires_on": wildcard,
    }


class TestGoodReadsImport:
    def setup_method(self, method):
        with open_test_data('goodreads_library_export.csv') as reader:
            self.csv_data = reader.read()

        self.expected_books = {
            "0142402494": {
                "Additional Authors": "Florence Lamborn, Louis S. Glanzman",
                "Author": "Astrid Lindgren",
                "Author l-f": "Lindgren, Astrid",
                "Average Rating": "4.13",
                "BCID": "",
                "Binding": "Mass Market Paperback",
                "Book Id": "19302",
                "Bookshelves": "to-read",
                "Bookshelves with positions": "to-read (#2)",
                "Condition": "",
                "Condition Description": "",
                "Date Added": "2020/12/13",
                "Date Read": "",
                "Exclusive Shelf": "to-read",
                "ISBN": "0142402494",
                "ISBN13": "9780142402498",
                "My Rating": "0",
                "My Review": "",
                "Number of Pages": "160",
                "Original Publication Year": "1945",
                "Original Purchase Date": "",
                "Original Purchase Location": "",
                "Owned Copies": "0",
                "Private Notes": "",
                "Publisher": "Puffin Books",
                "Read Count": "0",
                "Recommended By": "",
                "Recommended For": "",
                "Spoiler": "",
                "Title": "Pippi Longstocking (Pippi Långstrump, #1)",
                "Year Published": "2005",
            },
            "0735214484": {
                "Additional Authors": "",
                "Author": "David   Epstein",
                "Author l-f": "Epstein, David",
                "Average Rating": "4.16",
                "BCID": "",
                "Binding": "Hardcover",
                "Book Id": "41795733",
                "Bookshelves": "to-read",
                "Bookshelves with positions": "to-read (#1)",
                "Condition": "",
                "Condition Description": "",
                "Date Added": "2020/12/13",
                "Date Read": "",
                "Exclusive Shelf": "to-read",
                "ISBN": "0735214484",
                "ISBN13": "9780735214484",
                "My Rating": "0",
                "My Review": "",
                "Number of Pages": "352",
                "Original Publication Year": "2019",
                "Original Purchase Date": "",
                "Original Purchase Location": "",
                "Owned Copies": "0",
                "Private Notes": "",
                "Publisher": "Riverhead Books",
                "Read Count": "0",
                "Recommended By": "",
                "Recommended For": "",
                "Spoiler": "",
                "Title": "Range: Why Generalists Triumph in a Specialized World",
                "Year Published": "2019",
            },
        }

        self.expected_books_wo_isbns = {
            "99999999999": {
                "Additional Authors": "",
                "Author": "AuthorWith NoISBN",
                "Author l-f": "NoISBN, AuthorWith",
                "Average Rating": "4.16",
                "BCID": "",
                "Binding": "Hardcover",
                "Book Id": "99999999999",
                "Bookshelves": "to-read",
                "Bookshelves with positions": "to-read (#1)",
                "Condition": "",
                "Condition Description": "",
                "Date Added": "2020/12/13",
                "Date Read": "",
                "Exclusive Shelf": "to-read",
                "ISBN": "",
                "ISBN13": "",
                "My Rating": "0",
                "My Review": "",
                "Number of Pages": "352",
                "Original Publication Year": "2019",
                "Original Purchase Date": "",
                "Original Purchase Location": "",
                "Owned Copies": "0",
                "Private Notes": "",
                "Publisher": "Test Publisher",
                "Read Count": "0",
                "Recommended By": "",
                "Recommended For": "",
                "Spoiler": "",
                "Title": "Test Book Title With No ISBN",
                "Year Published": "2019",
            }
        }

    @pytest.mark.skipif(
        sys.version_info < (3, 0), reason="Python2's csv module doesn't support Unicode"
    )
    def test_process_goodreads_csv_with_utf8(self):
        books, books_wo_isbns = account.process_goodreads_csv(
            web.storage({'csv': self.csv_data.decode('utf-8')})
        )
        assert books == self.expected_books
        assert books_wo_isbns == self.expected_books_wo_isbns

    def test_process_goodreads_csv_with_bytes(self):
        # Note: In Python2, reading data as bytes returns a string, which should
        # also be supported by account.process_goodreads_csv()
        books, books_wo_isbns = account.process_goodreads_csv(
            web.storage({'csv': self.csv_data})
        )
        assert books == self.expected_books
        assert books_wo_isbns == self.expected_books_wo_isbns


@pytest.mark.xfail
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
        """Attempt login and return True if successful."""
        b.open("/account/login")
        b.select_form(name="register")  # wrong name
        b["username"] = username
        b["password"] = password
        b.submit()

        return b.path == "/"

    def test_create(self, ol):
        b = ol.browser()
        self.signup(
            b,
            displayname="Foo",
            username="foo",
            password="blackgoat",
            email="foo@example.com",
        )

        assert "Hi, foo!" in b.get_text(id="contentHead")
        assert "sent an email to foo@example.com" in b.get_text(id="contentBody")

        assert ol.sentmail["from_address"] == "Open Library <noreply@archive.org>"
        assert ol.sentmail["to_address"] == "foo@example.com"
        assert ol.sentmail["subject"] == "Welcome to Open Library"
        link = ol.sentmail.extract_links()[0]

        assert re.match("^http://0.0.0.0:8080/account/verify/[0-9a-f]{32}$", link)

    def test_activate(self, ol):
        b = ol.browser()

        self.signup(
            b,
            displayname="Foo",
            username="foo",
            password="secret",
            email="foo@example.com",
        )
        link = ol.sentmail.extract_links()[0]
        b.open(link)

        assert "Hi, Foo!" in b.get_text(id="contentHead")
        assert "Yay! Your email address has been verified." in b.get_text(
            id="contentBody"
        )

        self.login(b, "foo", "secret")

        assert b.path == "/"
        assert "Log out" in b.get_text()

    def test_forgot_password(self, ol):
        b = ol.browser()

        self.signup(
            b,
            displayname="Foo",
            username="foo",
            password="secret",
            email="foo@example.com",
        )
        link = ol.sentmail.extract_links()[0]
        b.open(link)

        b.open("/account/password/forgot")
        b.select_form(name="register")  # why is the form called register?
        b['email'] = "foo@example.com"
        b.submit()

        assert "Thanks" in b.get_text(id="contentHead")
        assert "We've sent an email to foo@example.com with instructions" in b.get_text(
            id="contentBody"
        )

        link = ol.sentmail.extract_links()[0]
        assert re.match(
            "^http://0.0.0.0:8080/account/password/reset/[0-9a-f]{32}$", link
        )

        b.open(link)
        assert "Reset Password" in b.get_text(id="contentHead")
        assert (
            "Please enter a new password for your Open Library account"
            in b.get_text(id="contentBody")
        )
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
        self.signup(
            b,
            displayname="Foo",
            username="foo",
            password="secret",
            email="foo@example.com",
        )
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
        assert self.login(b, "foo", "more_secret") is True

    def test_change_email(self, ol):
        b = ol.browser()
        self.signup(
            b,
            displayname="Foo",
            username="foo",
            password="secret",
            email="foo@example.com",
        )

        link = ol.sentmail.extract_links()[0]
        b.open(link)

        self.login(b, "foo", "secret")

        b.open("/account/email")

        assert "foo@example.com" in b.data

        b.select_form(name="register")
        b['email'] = "foobar@example.com"
        b.submit()

        assert "Hi Foo" in b.get_text(id="contentHead")
        assert "We've sent an email to foobar@example.com" in b.get_text(
            id="contentBody"
        )

        link = ol.sentmail.extract_links()[0]
        b.open(link)
        assert "Email verification successful" in b.get_text(id="contentHead")

        b.open("/account/email")
        assert "foobar@example.com" in b.data
