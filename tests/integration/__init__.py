import time
import yaml
import atexit
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException


class OLSession:
    def __init__(self, timeout=10, domain="https://dev.openlibrary.org"):
        with open('auth.yaml') as f:
            self.config = yaml.load(f)
        try:
            self.driver = webdriver.Chrome()
        except:
            self.driver = webdriver.Firefox()

        self.driver.set_window_size(1200, 1200)
        self.driver.implicitly_wait(timeout)
        self.wait = WebDriverWait(self.driver, timeout)
        self._url = self.config.get('url', domain)
        atexit.register(lambda: self.driver.close())

    @property
    def selenium_selector(self):
        return By

    def url(self, uri=""):
        return f"{self._url}/{uri}"

    def goto(self, uri=""):
        self.driver.get(self.url(uri))

    def ia_login(
        self, email, password, test=None, domain="https://archive.org", **kwargs
    ):
        self.driver.get('%s/account/login.php' % domain)
        self.driver.find_element_by_id('username').send_keys(email)
        self.driver.find_element_by_id('password').send_keys(password)
        self.driver.find_element_by_name('submit').click()
        if test:
            assert (
                self.ia_is_logged_in()
            ), f"IA Login failed w/ username: {email} and password: {password}"

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
            assert not self.ia_is_logged_in(), "Failed to logout of IA"

    def login(self, email, password, test=None, **kwargs):
        self.driver.get(self.url('/account/login'))
        self.driver.find_element_by_id("username").send_keys(email)
        self.driver.find_element_by_id("password").send_keys(password)
        self.driver.find_element_by_name('login').click()
        if test:
            assert (
                self.is_logged_in()
            ), f"OL Login failed w/ username: {email} and password: {password}"

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
            '#headerUserOpen > a:nth-child(5)'
        ).click()
        self.driver.get(self.url('/account/login'))
        if test:
            assert not self.is_logged_in(), "Failed to logout of OL"

    def connect(self, email, password):
        self.wait_for_clickable('linkAccounts')
        self.driver.find_element_by_id('linkAccounts').click()
        self.driver.find_element_by_id('bridgeEmail').send_keys(email)
        self.driver.find_element_by_id('bridgePassword').send_keys(password)
        self.driver.find_element_by_id('verifyAndConnect').click()
        time.sleep(1)

    def create(self, username=None):
        self.driver.execute_script(
            "document.getElementById('debug_token').value='"
            + self.config['internal_tests_api_key']
            + "'"
        )
        time.sleep(1)
        self.wait_for_clickable('createAccount')
        self.driver.find_element_by_id('createAccount').click()
        time.sleep(1)

    def unlink(self, email):
        import requests

        email = email.replace('+', '%2b')
        r = requests.get(
            self.url(
                '/internal/account/audit?key=%s&email=%s&unlink=true'
                % (self.config['internal_tests_api_key'], email)
            )
        )

    def wait_for_clickable(self, css_id, by=By.ID):
        self.wait.until(EC.element_to_be_clickable((by, css_id)))

    def wait_for_visible(self, css_id, by=By.ID):
        self.wait.until(EC.visibility_of_element_located((by, css_id)))
