#-*- encoding: utf-8 -*-

import pytest
from splinter import Browser

class TestSearch:
    # host = 'https://openlibrary.org'
    host = 'http://localhost:8080'

    @pytest.fixture
    def browser(self):
        browser = Browser('chrome')
        yield browser
        browser.quit()

    def test_search_inside(self, browser):
        browser.visit(self.host)
        browser.click_link_by_text('Search inside all Internet Archive books')
        browser.find_by_css(".searchInsideForm > input[name='q']").fill('homer')
        browser.find_by_css(".searchInsideForm > input[type='submit']").click()
        # No Elastic Search in test rig, so expect to return error message
        assert browser.is_element_present_by_css("[class='searchResultsError']")
