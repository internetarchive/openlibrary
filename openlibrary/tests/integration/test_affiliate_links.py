import pytest
from splinter import Browser


class TestAffiliateLinks:
    # host = 'https://openlibrary.org'
    host = 'http://localhost:8080'

    @pytest.fixture()
    def browser(self):
        browser = Browser('chrome')
        yield browser
        browser.quit()

    def test_affiliate_links_on_work(self, browser):
        url = self.host + '/works/OL6037022W/Remix'
        browser.visit(url)
        assert browser.is_element_present_by_css(
            "a[href*='www.amazon.com/dp/1408113473/?tag=internetarchi-20']"
        )
        assert browser.is_element_present_by_css("a[href*='www.betterworldbooks.com']")

    def test_affiliate_links_on_edition(self, browser):
        url = self.host + '/books/OL24218235M/Remix'
        browser.visit(url)
        assert browser.is_element_present_by_css(
            "a[href*='www.amazon.com/dp/1408113473/?tag=internetarchi-20']"
        )
        assert browser.is_element_present_by_css("a[href*='www.betterworldbooks.com']")
