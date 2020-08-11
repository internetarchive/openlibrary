# -*- coding: utf-8 -*-

import atexit
import os
import time

import yaml
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class OLSession(object):
    def __init__(self, timeout=10, domain="https://dev.openlibrary.org"):
        # set 'here' to 'openlibrary/tests/integration' regardless of working directory
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, '../../conf/openlibrary.yml')) as f:
            self.config = yaml.load(f, Loader=yaml.SafeLoader)
            OPENLIBRARY_USER_AUTH = {
                'email': 'openlibrary@example.com',
                'password': self.config.get('admin_password', 'password'),
            }
            self.config['accounts'] = {
                'ia_blocked': OPENLIBRARY_USER_AUTH,
                'ia_unverified': OPENLIBRARY_USER_AUTH,
                'ia_verified': 'abc',
                'ia_verified_mixedcase': 'abc',
                'ia_create': "tryme",
                'ia_create_conflict': True,

                'ol_blocked': OPENLIBRARY_USER_AUTH,
                'ol_unverified': 'abc',
                'ol_verified': 'abc',
                'ol_create': 'tryme',
                'ol_create_conflict': True,

                'linked': OPENLIBRARY_USER_AUTH,
                'linked_blocked': True,

                'unregistered': True,

                'live1': OPENLIBRARY_USER_AUTH,
                'live2': OPENLIBRARY_USER_AUTH,
                'live3': OPENLIBRARY_USER_AUTH,
            }
        try:
            self.driver = webdriver.Chrome()
        except WebDriverException:
            self.driver = webdriver.Firefox()
        assert self.driver

        self.driver.set_window_size(1200, 1200)
        self.driver.implicitly_wait(timeout)
        self.wait = WebDriverWait(self.driver, timeout)
        self._url = self.config.get('url', domain)
        atexit.register(lambda: self.driver.close())

    @property
    def selenium_selector(self):
        return By

    def url(self, uri=""):
        return "%s/%s" % (self._url, uri)

    def goto(self, uri=""):
        self.driver.get(self.url(uri))

    def ia_login(self, email, password, test=None,
                 domain="https://archive.org", **kwargs):
        self.driver.get('%s/account/login.php' % domain)
        self.driver.find_element_by_id('username').send_keys(email)
        self.driver.find_element_by_id('password').send_keys(password)
        self.driver.find_element_by_name('submit').click()
        if test:
            test.assertTrue(
                self.ia_is_logged_in(),
                "IA Login failed w/ username: %s and password: %s" %
                (email, password))

    def ia_is_logged_in(self, domain="https://archive.org"):
        time.sleep(2)
        self.driver.get('%s/account/' % domain)
        try:
            pagecontent = self.driver.find_element_by_class_name('welcome')
        except NoSuchElementException:
            return False
        return True

    def ia_logout(self, test=None, domain="https://archive.org"):
        self.driver.get('%s/account/logout.php' % domain)
        if test:
            test.assertTrue(not self.ia_is_logged_in(),
                            "Failed to logout of IA")

    def login(self, email, password, test=None, **kwargs):
        self.driver.get(self.url('/account/login'))
        self.driver.find_element_by_id("username").send_keys(email)
        self.driver.find_element_by_id("password").send_keys(password)
        self.driver.find_element_by_name('login').click()
        if test:
            test.assertTrue(self.is_logged_in(),
                "OL Login failed w/ username: %s and password: %s" %
                (email, password))

    def is_logged_in(self):
        time.sleep(2)
        try:
            self.driver.find_element_by_id('userToggle')
        except NoSuchElementException:
            return False
        return True

    def logout(self, test=None):
        time.sleep(2)
        self.wait.until(EC.element_to_be_clickable((By.ID, 'userToggle'))).click()
        self.driver.find_element_by_css_selector(
            '#headerUserOpen > a:nth-child(5)').click()
        self.driver.get(self.url('/account/login'))
        if test:
            test.assertTrue(not self.is_logged_in(),
                            "Failed to logout of OL")

    def connect(self, email, password):
        self.wait_for_clickable('linkAccounts')
        self.driver.find_element_by_id('linkAccounts').click()
        self.driver.find_element_by_id('bridgeEmail').send_keys(email)
        self.driver.find_element_by_id('bridgePassword').send_keys(password)
        self.driver.find_element_by_id('verifyAndConnect').click()
        time.sleep(1)

    def create(self, username=None):
        self.driver.execute_script(
            "document.getElementById('debug_token').value='" +
            self.config['internal_tests_api_key'] + "'");
        time.sleep(1)
        self.wait_for_clickable('createAccount')
        self.driver.find_element_by_id('createAccount').click()
        time.sleep(1)

    def unlink(self, email):
        import requests
        email = email.replace('+', '%2b')
        r = requests.get(self.url('/internal/account/audit?key=%s&email=%s&unlink=true'
               % (self.config['internal_tests_api_key'], email)))

    def wait_for_clickable(self, css_id, by=By.ID):
        self.wait.until(EC.element_to_be_clickable((by, css_id)))

    def wait_for_visible(self, css_id, by=By.ID):
        self.wait.until(EC.visibility_of_element_located((by, css_id)))
