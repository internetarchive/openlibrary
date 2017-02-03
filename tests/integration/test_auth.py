#-*- coding: utf-8 -*-

"""
ol/ia auth bridge tests
"""

import time
import atexit
import unittest
import yaml
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException


with open('auth.yaml', 'r') as f:
    config = yaml.load(f)

URL =  config['url']
internal_api_key = config['internal_api_key']

# =========
# Accounts
# =========

IA_BLOCKED = config['accounts']['ia_blocked']
IA_UNVERIFIED = config['accounts']['ia_unverified']
IA_VERIFIED = config['accounts']['ia_verified']
IA_CREATE = config['accounts']['ia_create']
IA_CREATE_CONFLICT = config['accounts']['ia_create_conflict']

OL_BLOCKED = config['accounts']['ol_blocked']
OL_UNVERIFIED = config['accounts']['ol_unverified']
OL_VERIFIED = config['accounts']['ol_verified']
OL_CREATE = config['accounts']['ol_create']
OL_CREATE_CONFLICT = config['accounts']['ol_create_conflict']

LINKED = config['accounts']['linked']
LINKED_BLOCKED = config['accounts']['linked_blocked']

UNREGISTERED = config['accounts']['unregistered']


try:
    driver = webdriver.Chrome()
except:
    driver = webdriver.Firefox()

driver.implicitly_wait(20)
wait = WebDriverWait(driver, 15)

def cleanup():
    global driver
    driver.close()

atexit.register(cleanup)

class Xauth_Test(unittest.TestCase):

    def login(self, email, password):
        driver.get(URL + '/account/login')
        driver.find_element_by_id("username").send_keys(email)
        driver.find_element_by_id("password").send_keys(password)
        driver.find_element_by_name('login').click()

    def logout(self):
        time.sleep(2)
        wait.until(EC.element_to_be_clickable((By.ID, 'userToggle'))).click()
        driver.find_element_by_css_selector(
            '#headerUserOpen > a:nth-child(5)').click()

    def is_logged_in(self):
        time.sleep(2)
        try:
            driver.find_element_by_id('userToggle')
        except NoSuchElementException:
            return False
        return True

    def connect(self, email, password):
        wait.until(EC.element_to_be_clickable((By.ID, 'linkAccounts')))
        driver.find_element_by_id('linkAccounts').click()
        driver.find_element_by_id('bridgeEmail').send_keys(email)
        driver.find_element_by_id('bridgePassword').send_keys(password)
        driver.find_element_by_id('verifyAndConnect').click()
        time.sleep(1)

    def create(self, username=None):
        driver.execute_script(
            "document.getElementById('debug_token').value='" + internal_api_key + "'");
        time.sleep(1)
        wait.until(EC.element_to_be_clickable((By.ID, 'createAccount')))
        driver.find_element_by_id('createAccount').click()
        if username:
            wait.until(EC.element_to_be_clickable((By.ID, 'bridgeUsername')))
            driver.find_element_by_id('bridgeUsername').send_keys(username)
        wait.until(EC.element_to_be_clickable((By.ID, 'verifyAndCreate')))
        driver.find_element_by_id('verifyAndCreate').click()
        time.sleep(1)

    def unlink(self, email):
        import requests
        email = email.replace('+', '%2b')
        url = ('%s/internal/account/unlink?key=%s&email=%s'
               % (URL, internal_api_key, email))
        r = requests.get(url)

    def test_empty_submit(self):
        self.login(u'', u'')
        _error = "The email address you entered is invalid"
        error = driver.find_element_by_class_name('note').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_missing_email(self):
        self.login(u'', u'password')
        _error = "The email address you entered is invalid"
        error = driver.find_element_by_class_name('note').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_invalid_email(self):
        self.login(u'invalid_email', u'password')
        _error = "The email address you entered is invalid"
        error = driver.find_element_by_class_name('note').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_unregistered_email(self):
        self.login(u'mek+invalid_email@archive.org', u'password')
        _error = "No account could be found matching these credentials"
        error = driver.find_element_by_class_name('note').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))


    # ======================================================
    # Test successfully linked account
    # ======================================================

    def test_linked(self):
        self.unlink(LINKED['email'])
        self.login(**LINKED)
        self.assertTrue(self.is_logged_in())
        self.logout()
        self.assertTrue(not self.is_logged_in())
        self.login(**LINKED)
        self.assertTrue(self.is_logged_in())
        self.logout()

        # finalize by unlinking for future tests
        self.unlink(LINKED['email'])


    # ======================================================
    # All combos of initial IA login audit
    # ======================================================

    def test_ia_missing_password(self):
        self.login(IA_VERIFIED['email'], u'password')
        _error = "The login credentials you entered are invalid"
        error = driver.find_element_by_class_name('note').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ia_incorrect_password(self):
        self.login(IA_VERIFIED['email'], u'password')
        _error = "The login credentials you entered are invalid"
        error = driver.find_element_by_class_name('note').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ia_blocked(self):
        self.login(**IA_BLOCKED)
        _error = "This account has been blocked"
        error = driver.find_element_by_class_name('note').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ia_blocked_incorrect_password(self):
        self.login(IA_BLOCKED['email'], '')
        _error = "The login credentials you entered are invalid"
        error = driver.find_element_by_class_name('note').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ia_unverified(self):
        self.login(**IA_UNVERIFIED)
        _error = "This account must be verified before login can be completed"
        error = driver.find_element_by_class_name('note').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))


    # ======================================================
    # All combos of initial OL login audit
    # ======================================================

    def test_ol_missing_password(self):
        self.login(OL_VERIFIED['email'], u'password')
        _error = "The login credentials you entered are invalid"
        error = driver.find_element_by_class_name('note').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ol_incorrect_password(self):
        self.login(OL_VERIFIED['email'], u'password')
        _error = "The login credentials you entered are invalid"
        error = driver.find_element_by_class_name('note').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ol_blocked(self):
        self.login(**OL_BLOCKED)
        _error = "This account has been blocked"
        error = driver.find_element_by_class_name('note').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ol_blocked_incorrect_password(self):
        self.login(OL_BLOCKED['email'], 'password')
        _error = "This account has been blocked"
        error = driver.find_element_by_class_name('note').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ol_unverified(self):
        self.login(**OL_UNVERIFIED)
        _error = "This account must be verified before login can be completed"
        error = driver.find_element_by_class_name('note').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))


    # ======================================================
    # All combinations of connect attempts after initial
    # successful audit for an IA account
    # ======================================================

    def test_ia_verified_connect_invalid_email(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**IA_VERIFIED)
        self.connect(OL_VERIFIED['email'], 'password')
        wait.until(
            EC.visibility_of_element_located((By.ID, 'connectError')))
        _error = "The login credentials you entered are invalid"
        error = driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ia_verified_connect_unregistered_email(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**IA_VERIFIED)
        self.connect(**UNREGISTERED)
        wait.until(
            EC.visibility_of_element_located((By.ID, 'connectError')))
        _error = "No account could be found matching these credentials"
        error = driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ia_verified_connect_missing_email(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**IA_VERIFIED)
        self.connect('', 'password')
        wait.until(
            EC.visibility_of_element_located((By.ID, 'connectError')))
        _error = "Please fill out all fields and try again"
        error = driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ia_verified_connect_ol_missing_password(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**IA_VERIFIED)
        self.connect(OL_VERIFIED['email'], '')
        wait.until(
            EC.visibility_of_element_located((By.ID, 'connectError')))
        _error = "Please fill out all fields and try again"
        error = driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ia_verified_connect_ia_missing_password(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**IA_VERIFIED)
        self.connect(IA_VERIFIED['email'], 'password')
        wait.until(
            EC.visibility_of_element_located((By.ID, 'connectError')))
        _error = "No account could be found matching these credentials"
        error = driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ia_verified_connect_ol_incorrect_password(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**IA_VERIFIED)
        self.connect(OL_VERIFIED['email'], 'password')
        wait.until(
            EC.visibility_of_element_located((By.ID, 'connectError')))
        _error = "The login credentials you entered are invalid"
        error = driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ia_verified_connect_ia_incorrect_password(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**IA_VERIFIED)
        self.connect(IA_VERIFIED['email'], 'password')
        wait.until(
            EC.visibility_of_element_located((By.ID, 'connectError')))
        _error = "No account could be found matching these credentials"
        error = driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ia_verified_connect_ol_blocked(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**IA_VERIFIED)
        self.connect(**OL_BLOCKED)
        wait.until(
            EC.visibility_of_element_located((By.ID, 'connectError')))
        _error = "This account has been blocked"
        error = driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ia_verified_connect_ia_blocked(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**IA_VERIFIED)
        self.connect(**IA_BLOCKED)
        wait.until(
            EC.visibility_of_element_located((By.ID, 'connectError')))
        _error = "No account could be found matching these credentials"
        error = driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ia_verified_connect_linked_blocked(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**IA_VERIFIED)
        self.connect(**LINKED_BLOCKED)
        wait.until(
            EC.visibility_of_element_located((By.ID, 'connectError')))
        _error = "This account has been blocked"
        error = driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ia_verified_connect_ol_linked(self):
        # Link LINKED accounts
        self.unlink(LINKED['email'])
        self.login(**LINKED)
        self.assertTrue(self.is_logged_in())
        self.logout()

        self.unlink(OL_VERIFIED['email'])
        self.login(**IA_VERIFIED)
        self.connect(**LINKED)
        wait.until(
            EC.visibility_of_element_located((By.ID, 'connectError')))
        _error = "This account has already been linked"
        error = driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

        # finalize by unlinking for future tests
        self.unlink(LINKED['email'])
        self.unlink(OL_VERIFIED['email'])

    def test_ia_verified_connect_ol_unverified(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**IA_VERIFIED)
        self.connect(**OL_UNVERIFIED)
        wait.until(
            EC.visibility_of_element_located((By.ID, 'connectError')))
        _error = "This account must be verified before login can be completed"
        error = driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ia_verified_connect_ia_unverified(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**IA_VERIFIED)
        self.connect(**IA_UNVERIFIED)
        wait.until(
            EC.visibility_of_element_located((By.ID, 'connectError')))
        _error = "No account could be found matching these credentials"
        error = driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ia_verified_connect_ia_verified(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**IA_VERIFIED)
        self.connect(**IA_VERIFIED)
        wait.until(
            EC.visibility_of_element_located((By.ID, 'connectError')))
        _error = "No account could be found matching these credentials"
        error = driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ia_verified_connect_ol_verified(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**IA_VERIFIED)
        self.connect(**OL_VERIFIED)
        self.assertTrue(self.is_logged_in())
        self.logout()
        self.assertTrue(not self.is_logged_in())
        self.login(**IA_VERIFIED)
        self.assertTrue(self.is_logged_in())
        self.logout()
        self.assertTrue(not self.is_logged_in())
        self.login(**OL_VERIFIED)
        self.assertTrue(self.is_logged_in())
        self.logout()

        # finalize by unlinking for future tests
        self.unlink(OL_VERIFIED['email'])


    # ======================================================
    # All combinations of connect attempts after initial
    # successful audit for an OL account
    # ======================================================

    def test_ol_verified_connect_invalid_email(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**OL_VERIFIED)
        self.connect(IA_VERIFIED['email'], 'password')
        wait.until(
            EC.visibility_of_element_located((By.ID, 'connectError')))
        _error = "The login credentials you entered are invalid"
        error = driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ol_verified_connect_unregistered_email(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**OL_VERIFIED)
        self.connect(**UNREGISTERED)
        wait.until(
            EC.visibility_of_element_located((By.ID, 'connectError')))
        _error = "No account could be found matching these credentials"
        error = driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ol_verified_connect_missing_email(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**OL_VERIFIED)
        self.connect('', 'password')
        wait.until(
            EC.visibility_of_element_located((By.ID, 'connectError')))
        _error = "Please fill out all fields and try again"
        error = driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ol_verified_connect_ia_missing_password(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**OL_VERIFIED)
        self.connect(IA_VERIFIED['email'], '')
        wait.until(
            EC.visibility_of_element_located((By.ID, 'connectError')))
        _error = "Please fill out all fields and try again"
        error = driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ol_verified_connect_ol_incorrect_password(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**OL_VERIFIED)
        self.connect(OL_VERIFIED['email'], 'password')
        wait.until(
            EC.visibility_of_element_located((By.ID, 'connectError')))
        _error = "No account could be found matching these credentials"
        error = driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ol_verified_connect_ia_incorrect_password(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**OL_VERIFIED)
        self.connect(IA_VERIFIED['email'], 'password')
        wait.until(
            EC.visibility_of_element_located((By.ID, 'connectError')))
        _error = "The login credentials you entered are invalid"
        error = driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ol_verified_connect_ol_blocked(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**OL_VERIFIED)
        self.connect(**OL_BLOCKED)
        wait.until(
            EC.visibility_of_element_located((By.ID, 'connectError')))
        _error = "No account could be found matching these credentials"
        error = driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ol_verified_connect_ia_blocked(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**OL_VERIFIED)
        self.connect(**IA_BLOCKED)
        wait.until(
            EC.visibility_of_element_located((By.ID, 'connectError')))
        _error = "This account has been blocked"
        error = driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ol_verified_connect_ol_blocked_linked(self):
        self.unlink(IA_VERIFIED['email'])
        self.login(**OL_VERIFIED)
        self.connect(**LINKED_BLOCKED)
        wait.until(
            EC.visibility_of_element_located((By.ID, 'connectError')))
        _error = "This account has been blocked"
        error = driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ol_verified_connect_ol_linked(self):
        # Link LINKED accounts
        self.unlink(LINKED['email'])
        self.login(**LINKED)
        self.assertTrue(self.is_logged_in())
        self.logout()

        self.unlink(OL_VERIFIED['email'])
        self.login(**OL_VERIFIED)
        self.connect(**LINKED)
        wait.until(
            EC.visibility_of_element_located((By.ID, 'connectError')))
        _error = "This account has already been linked"
        error = driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

        # finalize by unlinking for future tests
        self.unlink(LINKED['email'])
        self.unlink(OL_VERIFIED['email'])

    def test_ol_verified_connect_ol_unverified(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**OL_VERIFIED)
        self.connect(**OL_UNVERIFIED)
        wait.until(
            EC.visibility_of_element_located((By.ID, 'connectError')))
        _error = "No account could be found matching these credentials"
        error = driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ol_verified_connect_ia_unverified(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**OL_VERIFIED)
        self.connect(**IA_UNVERIFIED)
        wait.until(
            EC.visibility_of_element_located((By.ID, 'connectError')))
        _error = "This account must be verified before login can be completed"
        error = driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ol_verified_connect_ol_verified(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**OL_VERIFIED)
        self.connect(**OL_VERIFIED)
        wait.until(
            EC.visibility_of_element_located((By.ID, 'connectError')))
        _error = "No account could be found matching these credentials"
        error = driver.find_element_by_id('connectError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ol_verified_connect_ia_verified(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**OL_VERIFIED)
        self.connect(**IA_VERIFIED)
        self.assertTrue(self.is_logged_in())
        self.logout()
        self.assertTrue(not self.is_logged_in())
        self.login(**OL_VERIFIED)
        self.assertTrue(self.is_logged_in())
        self.logout()
        self.assertTrue(not self.is_logged_in())
        self.login(**IA_VERIFIED)
        self.assertTrue(self.is_logged_in())
        self.logout()

        # finalize by unlinking for future tests
        self.unlink(OL_VERIFIED['email'])

"""
    The following tests are deprecated until the "test" / developer
    settings are sophisticated to accommodate idempotent testing of
    user creation. The "create_empty" and "username_registered" cases
    are deprected because we now retry 5 times with different
    usernames... We could register 5 accounts,
    e.g. mek+test0@archive.org - mek+test4@archive.org but this seems
    overkill.

    # ======================================================
    # All combinations of Create & Link attempts after initial
    # successful audit from an IA account
    # ======================================================

    def test_ia_verified_create_empty_submit(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**IA_CREATE_CONFLICT)
        self.create('')
        driver.find_element_by_id('bridgeUsername').clear()
        wait.until(EC.element_to_be_clickable((By.ID, 'verifyAndCreate')))
        driver.find_element_by_id('verifyAndCreate').click()
        time.sleep(1)
        wait.until(
            EC.visibility_of_element_located((By.ID, 'createError')))
        _error = "Please fill out all fields and try again"
        error = driver.find_element_by_id('createError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ia_verified_create_registered_screenname(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**IA_CREATE_CONFLICT)
        self.create('')
        wait.until(
            EC.visibility_of_element_located((By.ID, 'createError')))
        _error = "This username is already registered"
        error = driver.find_element_by_id('createError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ia_verified_create_ol_verified(self):
        self.login(**IA_CREATE)
        self.create()
        self.assertTrue(self.is_logged_in())
        self.logout()
        self.assertTrue(not self.is_logged_in())
        self.login(**IA_CREATE)
        self.assertTrue(self.is_logged_in())


    # ======================================================
    # All combinations of Create & Link attempts after initial
    # successful audit from an OL account
    # ======================================================

    def test_ol_verified_create_empty_submit(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**OL_CREATE_CONFLICT)
        self.create('')
        driver.find_element_by_id('bridgeUsername').clear()
        wait.until(EC.element_to_be_clickable((By.ID, 'verifyAndCreate')))
        driver.find_element_by_id('verifyAndCreate').click()
        time.sleep(1)
        wait.until(
            EC.visibility_of_element_located((By.ID, 'createError')))
        _error = "Please fill out all fields and try again"
        error = driver.find_element_by_id('createError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ol_verified_create_registered_screenname(self):
        self.unlink(OL_VERIFIED['email'])
        self.login(**OL_CREATE_CONFLICT)
        self.create('')
        wait.until(
            EC.visibility_of_element_located((By.ID, 'createError')))
        _error = "This username is already registered"
        error = driver.find_element_by_id('createError').text
        self.assertTrue(error == _error, '%s != %s' % (error, _error))

    def test_ol_verified_create_ia_verified(self):
        self.login(**OL_CREATE)
        self.create()
        self.assertTrue(self.is_logged_in())
        self.logout()
        self.assertTrue(not self.is_logged_in())
        self.login(**OL_CREATE)
        self.assertTrue(self.is_logged_in())
"""
