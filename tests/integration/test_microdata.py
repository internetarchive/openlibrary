#-*- encoding: utf-8 -*-

import pytest
from splinter import Browser

class TestMicrodata:

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

    def test_open_graph_metadata_on_work(self, browser):
        url = self.host + '/works/OL6037022W/Remix'
        browser.visit(url)
        assert browser.is_element_present_by_css("#content > div.contentContainer[itemtype='https://schema.org/Book']")

    def test_open_graph_metadata_on_editionk(self, browser):
        url = self.host + '/books/OL24218235M/Remix'
        browser.visit(url)
        assert browser.is_element_present_by_css("#contentBody[itemtype='https://schema.org/Book']")
