#-*- coding: utf-8 -*-

import time
import yaml
import atexit
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException


class OLSession(object):
    def __init__(self, timeout=20):
        with open('auth.yaml', 'r') as f:
            self.config = yaml.load(f)
        try:
            self.driver = webdriver.Chrome()
        except:
            self.driver = webdriver.Firefox()

        self.driver.implicitly_wait(timeout)
        self.wait = WebDriverWait(self.driver, timeout)
        self._url = config.get('url', 'https://dev.openlibrary.org')
        atexit.register(lambda: self.driver.close())

    def url(self, uri=""):
        return "%s/%s" % (self._url, uri)

    def goto(self, uri=""):
        self.driver.get(self.url(uri))

    def login(self, email, password, **kwargs):
        self.driver.get(self.url('/account/login'))
        self.driver.find_element_by_id("username").send_keys(email)
        self.driver.find_element_by_id("password").send_keys(password)
        self.driver.find_element_by_name('login').click()

    def is_logged_in(self):
        time.sleep(2)
        try:
            self.driver.find_element_by_id('userToggle')
        except NoSuchElementException:
            return False
        return True

    def logout(driver):
        time.sleep(2)
        self.wait.until(EC.element_to_be_clickable((By.ID, 'userToggle'))).click()
        self.driver.find_element_by_css_selector(
            '#headerUserOpen > a:nth-child(5)').click()
        self.driver.get(self.url('/account/login'))

    def connect(self, email, password):
        olsession.wait_for_clickable('linkAccounts')
        driver.find_element_by_id('linkAccounts').click()
        driver.find_element_by_id('bridgeEmail').send_keys(email)
        driver.find_element_by_id('bridgePassword').send_keys(password)
        driver.find_element_by_id('verifyAndConnect').click()
        time.sleep(1)

    def create(self, username=None):
        driver.execute_script(
            "document.getElementById('debug_token').value='" + 
            INTERNAL_TEST_API_URL + "'");
        time.sleep(1)
        olsession.wait_for_clickable('createAccount')
        driver.find_element_by_id('createAccount').click()
        time.sleep(1)

    def unlink(self, email):
        import requests
        email = email.replace('+', '%2b')
        r = requests.get(self.url('%s/internal/account/unlink?key=%s&email=%s'
               % (internal_tests_api_key, email)))

    def wait_for_clickable(self, css_id):
        self.wait.until(EC.element_to_be_clickable((By.ID, css_id)))

    def wait_for_visible(self, css_id):
        self.wait.until(EC.visibility_of_element_located((By.ID, css_id)))
