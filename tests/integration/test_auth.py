#-*- coding: utf-8 -*-

"""
ol/ia auth bridge tests
"""

import pytest
import unittest
from . import OLSession


olsession = OLSession()


# =========
# Accounts
# =========
IA_BLOCKED = olsession.config['accounts']['ia_blocked']
IA_UNVERIFIED = olsession.config['accounts']['ia_unverified']
IA_VERIFIED = olsession.config['accounts']['ia_verified']
IA_VERIFIED_MIXED = olsession.config['accounts']['ia_verified_mixedcase']
IA_CREATE = olsession.config['accounts']['ia_create']
IA_CREATE_CONFLICT = olsession.config['accounts']['ia_create_conflict']

OL_BLOCKED = olsession.config['accounts']['ol_blocked']
OL_UNVERIFIED = olsession.config['accounts']['ol_unverified']
OL_VERIFIED = olsession.config['accounts']['ol_verified']
OL_CREATE = olsession.config['accounts']['ol_create']
OL_CREATE_CONFLICT = olsession.config['accounts']['ol_create_conflict']

LINKED = olsession.config['accounts']['linked']
LINKED_BLOCKED = olsession.config['accounts']['linked_blocked']

UNREGISTERED = olsession.config['accounts']['unregistered']



errorLookup = {
    "invalid_email": "The email address you entered is invalid",
    "account_blocked": "This account has been blocked",
    "account_locked": "This account has been blocked",
    "account_not_found": "No account was found with this email. Please try again",
    "account_incorrect_password": "Wrong password. Please try again",
    "account_bad_password": "Wrong password. Please try again",
    "account_not_verified": "This account must be verified before login can be completed",
    "invalid_bridgeEmail": "Failed to link account: invalid email",
    "account_already_linked": "This account has already been linked",
    "missing_fields": "Please fill out all fields and try again",
    "email_registered": "This email is already registered",
    "username_registered": "This username is already registered",
    "max_retries_exceeded": "A problem occurred and we were unable to log you in."
}


class Xauth_Test(unittest.TestCase):


    # ======================================================
    # Basic tests
    # ======================================================

    def test_empty_submit(self):
        olsession.login(u'', u'')
        _error = errorLookup['invalid_email']
        error = olsession.driver.find_element_by_class_name('note').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_missing_email(self):
        olsession.login(u'', u'password')
        _error = errorLookup['invalid_email']
        error = olsession.driver.find_element_by_class_name('note').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_unregistered_email(self):
        olsession.login(u'mek+invalid_email@archive.org', u'password')
        _error = errorLookup['account_not_found']
        error = olsession.driver.find_element_by_class_name('note').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))


    # ======================================================
    # Test successfully linked account
    # ======================================================

    @pytest.mark.xfail(reason="TODO: AssertionError")
    def test_linked(self):
        olsession.unlink(LINKED['email'])
        olsession.login(**LINKED)
        self.assertTrue(olsession.is_logged_in())
        olsession.logout()
        self.assertTrue(not olsession.is_logged_in())
        olsession.login(**LINKED)
        self.assertTrue(olsession.is_logged_in())
        olsession.logout()

        # finalize by unlinking for future tests
        olsession.unlink(LINKED['email'])


    # ======================================================
    # All combos of initial IA login audit
    # ======================================================

    @pytest.mark.xfail(reason="TODO: TypeError")
    def test_ia_missing_password(self):
        olsession.login(IA_VERIFIED['email'], u'password')
        _error = errorLookup['account_bad_password']
        error = olsession.driver.find_element_by_class_name('note').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    @pytest.mark.xfail(reason="TODO: TypeError")
    def test_ia_incorrect_password(self):
        olsession.login(IA_VERIFIED['email'], u'password')
        _error = errorLookup['account_bad_password']
        error = olsession.driver.find_element_by_class_name('note').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    @pytest.mark.xfail(reason="TODO: AssertionError")
    def test_ia_blocked(self):
        olsession.login(**IA_BLOCKED)
        _error = errorLookup['account_locked']
        error = olsession.driver.find_element_by_class_name('note').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    @pytest.mark.xfail(reason="TODO: AssertionError")
    def test_ia_blocked_incorrect_password(self):
        olsession.login(IA_BLOCKED['email'], '')
        _error = errorLookup['account_bad_password']
        error = olsession.driver.find_element_by_class_name('note').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    @pytest.mark.xfail(reason="TODO: AssertionError")
    def test_ia_unverified(self):
        olsession.login(**IA_UNVERIFIED)
        _error = errorLookup['account_not_verified']
        error = olsession.driver.find_element_by_class_name('note').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    # ======================================================
    # All combinations of connect attempts after initial
    # successful audit for an IA account
    # ======================================================

    @pytest.mark.xfail(reason="TODO: TypeError")
    def test_ia_verified_connect_ol_blocked(self):
        olsession.unlink(OL_VERIFIED['email'])
        olsession.login(**IA_VERIFIED)
        olsession.connect(**OL_BLOCKED)
        olsession.wait_for_visible('connectError')
        _error = errorLookup['account_blocked']
        error = olsession.driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    @pytest.mark.xfail(reason="TODO: AssertionError")
    def test_ia_verified_connect_ol_linked(self):
        # Link LINKED accounts
        olsession.unlink(LINKED['email'])
        olsession.login(**LINKED)
        self.assertTrue(olsession.is_logged_in())
        olsession.logout()

        olsession.unlink(OL_VERIFIED['email'])
        olsession.login(**IA_VERIFIED)
        olsession.connect(**LINKED)
        olsession.wait_for_visible('connectError')
        _error = errorLookup['account_already_linked']
        error = olsession.driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

        # finalize by unlinking for future tests
        olsession.unlink(LINKED['email'])
        olsession.unlink(OL_VERIFIED['email'])

    @pytest.mark.xfail(reason="TODO: TypeError")
    def test_ia_verified_connect_ol_unverified(self):
        olsession.unlink(OL_VERIFIED['email'])
        olsession.login(**IA_VERIFIED)
        olsession.connect(**OL_UNVERIFIED)
        olsession.wait_for_visible('connectError')
        _error = errorLookup['account_not_verified']
        error = olsession.driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    @pytest.mark.xfail(reason="TODO: TypeError")
    def test_ia_verified_connect_ia_unverified(self):
        olsession.unlink(OL_VERIFIED['email'])
        olsession.login(**IA_VERIFIED)
        olsession.connect(**IA_UNVERIFIED)
        olsession.wait_for_visible('connectError')
        _error = errorLookup['account_not_found']
        error = olsession.driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    @pytest.mark.xfail(reason="TODO: TypeError")
    def test_ia_verified_CASE(self):
        olsession.unlink(OL_VERIFIED['email'])
        olsession.login(**IA_VERIFIED_MIXED)
        olsession.connect(**OL_VERIFIED)
        self.assertTrue(olsession.is_logged_in())
        olsession.logout()
        olsession.unlink(OL_VERIFIED['email'])

    @pytest.mark.xfail(reason="TODO: TypeError")
    def test_ia_verified_connect_ia_verified(self):
        olsession.unlink(OL_VERIFIED['email'])
        olsession.login(**IA_VERIFIED)
        olsession.connect(**IA_VERIFIED)
        olsession.wait_for_visible('connectError')
        _error = errorLookup['account_not_found']
        error = olsession.driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    @pytest.mark.xfail(reason="TODO: TypeError")
    def test_ia_verified_connect_ol_verified(self):
        olsession.unlink(OL_VERIFIED['email'])
        olsession.login(**IA_VERIFIED)
        olsession.connect(**OL_VERIFIED)
        self.assertTrue(olsession.is_logged_in())
        olsession.logout()
        self.assertTrue(not olsession.is_logged_in())
        olsession.login(**IA_VERIFIED)
        self.assertTrue(olsession.is_logged_in())
        olsession.logout()
        self.assertTrue(not olsession.is_logged_in())
        olsession.login(**OL_VERIFIED)
        self.assertTrue(olsession.is_logged_in())
        olsession.logout()

        # finalize by unlinking for future tests
        olsession.unlink(OL_VERIFIED['email'])

    @pytest.mark.xfail(reason="TODO: TypeError")
    def test_ol_verified_connect_ol_blocked_linked(self):
        olsession.unlink(IA_VERIFIED['email'])
        olsession.login(**OL_VERIFIED)
        olsession.connect(**LINKED_BLOCKED)
        olsession.wait_for_visible('connectError')
        _error = errorLookup['account_blocked']
        error = olsession.driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    @pytest.mark.xfail(reason="TODO: AssertionError")
    def test_ol_verified_connect_ol_linked(self):
        # Link LINKED accounts
        olsession.unlink(LINKED['email'])
        olsession.login(**LINKED)
        self.assertTrue(olsession.is_logged_in())
        olsession.logout()

        olsession.unlink(OL_VERIFIED['email'])
        olsession.login(**OL_VERIFIED)
        olsession.connect(**LINKED)
        olsession.wait_for_visible('connectError')
        _error = errorLookup['account_already_linked']
        error = olsession.driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

        # finalize by unlinking for future tests
        olsession.unlink(LINKED['email'])
        olsession.unlink(OL_VERIFIED['email'])

    @pytest.mark.xfail(reason="TODO: TypeError")
    def test_ol_verified_connect_ol_unverified(self):
        olsession.unlink(OL_VERIFIED['email'])
        olsession.login(**OL_VERIFIED)
        olsession.connect(**OL_UNVERIFIED)
        olsession.wait_for_visible('connectError')
        _error = errorLookup['account_not_found']
        error = olsession.driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    @pytest.mark.xfail(reason="TODO: TypeError")
    def test_ol_verified_connect_ia_unverified(self):
        olsession.unlink(OL_VERIFIED['email'])
        olsession.login(**OL_VERIFIED)
        olsession.connect(**IA_UNVERIFIED)
        olsession.wait_for_visible('connectError')
        _error = errorLookup['account_not_verified']
        error = olsession.driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    @pytest.mark.xfail(reason="TODO: TypeError")
    def test_ol_verified_connect_ol_verified(self):
        olsession.unlink(OL_VERIFIED['email'])
        olsession.login(**OL_VERIFIED)
        olsession.connect(**OL_VERIFIED)
        olsession.wait_for_visible('connectError')
        _error = errorLookup['account_not_found']
        error = olsession.driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    @pytest.mark.xfail(reason="TODO: TypeError")
    def test_ol_verified_connect_ia_verified(self):
        olsession.unlink(OL_VERIFIED['email'])
        olsession.login(**OL_VERIFIED)
        olsession.connect(**IA_VERIFIED)
        self.assertTrue(olsession.is_logged_in())
        olsession.logout()
        self.assertTrue(not olsession.is_logged_in())
        olsession.login(**OL_VERIFIED)
        self.assertTrue(olsession.is_logged_in())
        olsession.logout()
        self.assertTrue(not olsession.is_logged_in())
        olsession.login(**IA_VERIFIED)
        self.assertTrue(olsession.is_logged_in())
        olsession.logout()

        # finalize by unlinking for future tests
        olsession.unlink(OL_VERIFIED['email'])


    # ======================================================
    # All combinations of Create & Link attempts after initial
    # successful audit from an IA account
    # ======================================================

    @pytest.mark.xfail(reason="TODO: TypeError")
    def test_ia_verified_create_registered_screenname(self):
        olsession.unlink(OL_VERIFIED['email'])
        olsession.login(**IA_CREATE_CONFLICT)
        olsession.create('')
        _error = errorLookup['max_retries_exceeded']
        error = olsession.driver.find_element_by_class_name('note').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    # ======================================================
    # All combinations of Create & Link attempts after initial
    # successful audit from an OL account
    # ======================================================

    @pytest.mark.xfail(reason="TODO: TypeError")
    def test_ol_verified_create_registered_screenname(self):
        olsession.unlink(OL_VERIFIED['email'])
        olsession.login(**OL_CREATE_CONFLICT)
        olsession.create('')
        _error = errorLookup['max_retries_exceeded']
        error = olsession.driver.find_element_by_class_name('note').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))
