import pytest
from splinter import Browser


class TestSearch:
    # host = 'https://openlibrary.org'
    host = 'http://localhost:8080'

    @pytest.fixture()
    def browser(self):
        browser = Browser('chrome')
        yield browser
        browser.quit()

    def test_search_inside(self, browser):
        browser.visit(self.host + '/search/inside')
        browser.find_by_css(".olform > input[name='q']").fill('black cat')
        browser.find_by_css(".olform > [type='submit']").click()
        assert browser.is_text_present('Search Inside')
        assert browser.is_element_present_by_css('.olform')

    def test_search_inside_from_global_nav(self, browser):
        browser.visit(self.host)
        browser.find_by_css("#headerSearch input[name='q']").fill('black cat')
        browser.find_by_css("#headerSearch input[name='search-fulltext']").check()
        browser.find_by_css("#headerSearch [type='submit']").click()
        assert browser.is_text_present('Search Inside')
        assert browser.is_element_present_by_css('.olform')

    def test_metadata_search(self, browser):
        browser.visit(self.host + '/search')
        browser.find_by_css(".siteSearch > input[name='q']").fill('remix')
        browser.find_by_css(".siteSearch > [type='submit']").click()
        assert browser.is_text_present('Search Results')
        assert browser.is_element_present_by_css('#searchResults li')

    def test_metadata_search_from_global_nav(self, browser):
        browser.visit(self.host)
        browser.find_by_css("#headerSearch input[name='q']").fill('remix')
        browser.find_by_css("#headerSearch input[type='submit']").click()
        assert browser.is_text_present('Search Results')
        assert browser.is_element_present_by_css('#searchResults li')
