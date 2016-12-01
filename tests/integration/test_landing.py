#-*- encoding: utf-8 -*-

import pytest
from splinter import Browser

class TestLanding:

    host = 'http://localhost:8080'

    def login(self, browser_instance):
        browser_instance.visit(self.host)
        browser_instance.find_link_by_text('Log in').first.click()
        browser_instance.fill('username', 'openlibrary')
        browser_instance.fill('password', 'openlibrary')
        browser_instance.find_by_value('Log In').first.click()

    @pytest.fixture
    def browser(self):
        browser = Browser('chrome')
        yield browser
        browser.quit()

    def test_popular_carousel(self, browser):
        url = self.host + '/'
        browser.visit(url)
        assert browser.is_element_present_by_css(".contentLists")


    def test_categories_carousel(self, browser):
        url = self.host + '/'
        browser.visit(url)
        assert browser.is_element_present_by_css(".categoryCarousel")
