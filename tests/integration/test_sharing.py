import pytest
from splinter import Browser


class TestSharing:
    # host = 'https://openlibrary.org'
    host = 'http://localhost:8080'

    def login(self, browser_instance):
        browser_instance.visit(self.host)
        browser_instance.find_link_by_text('Log in').first.click()
        browser_instance.fill('username', 'jessamyn@archive.org')
        browser_instance.fill('password', 'openlibrary')
        browser_instance.find_by_value('Log In').first.click()

    @pytest.fixture()
    def browser(self):
        browser = Browser('chrome')
        yield browser
        browser.quit()

    def test_open_graph_metadata_on_author(self, browser):
        url = self.host + '/authors/OL1518080A/Lawrence_Lessig'
        browser.visit(url)
        assert browser.is_element_present_by_css(
            "meta[property='og:title'][content*='Lawrence Lessig']"
        )
        assert browser.is_element_present_by_css(
            "meta[property='og:type'][content='books.author']"
        )
        assert browser.is_element_present_by_css(
            "meta[property='og:image'][content*='openlibrary.org/images']"
        )
        assert browser.is_element_present_by_css(
            "meta[property='og:url'][content*='authors/OL1518080A/Lawrence_Lessig']"
        )
        assert browser.is_element_present_by_css(
            "meta[property='og:site_name'][content='Open Library']"
        )
        assert browser.is_element_present_by_css(
            "meta[property='og:description'][content*='Lawrence Lessig']"
        )
        assert browser.is_element_present_by_css(
            "a[href*='facebook.com/sharer/sharer.php']"
        )
        assert browser.is_element_present_by_css("a[href*='twitter.com/intent/tweet']")

    def test_open_graph_metadata_on_work(self, browser):
        url = self.host + '/works/OL6037022W/Remix'
        browser.visit(url)
        assert browser.is_element_present_by_css(
            "meta[property='og:title'][content*='Remix']"
        )
        assert browser.is_element_present_by_css(
            "meta[property='og:type'][content='books.book']"
        )
        assert browser.is_element_present_by_css(
            "meta[property='og:image'][content*='openlibrary.org/images']"
        )
        assert browser.is_element_present_by_css(
            "meta[property='og:url'][content*='works/OL6037022W/Remix']"
        )
        assert browser.is_element_present_by_css(
            "meta[property='og:site_name'][content='Open Library']"
        )
        assert browser.is_element_present_by_css(
            "meta[property='og:description'][content*='Remix']"
        )
        assert browser.is_element_present_by_css(
            "a[href*='facebook.com/sharer/sharer.php']"
        )
        assert browser.is_element_present_by_css("a[href*='twitter.com/intent/tweet']")

    def test_open_graph_metadata_on_edition(self, browser):
        url = self.host + '/books/OL24218235M/Remix'
        browser.visit(url)
        assert browser.is_element_present_by_css(
            "meta[property='og:title'][content*='Remix']"
        )
        assert browser.is_element_present_by_css(
            "meta[property='og:type'][content='books.book']"
        )
        assert browser.is_element_present_by_css(
            "meta[property='og:image'][content*='.jpg']"
        )
        assert browser.is_element_present_by_css(
            "meta[property='og:url'][content*='books/OL24218235M/Remix']"
        )
        assert browser.is_element_present_by_css(
            "meta[property='og:site_name'][content='Open Library']"
        )
        assert browser.is_element_present_by_css(
            "meta[property='og:description'][content*='Remix']"
        )
        assert browser.is_element_present_by_css(
            "a[href*='facebook.com/sharer/sharer.php']"
        )
        assert browser.is_element_present_by_css("a[href*='twitter.com/intent/tweet']")

    def test_open_graph_metadata_on_list(self, browser):
        """Assumes that one list has been created with Remix as its entry"""
        browser.visit(self.host + '/lists')
        browser.find_by_css('.changeHistory a').first.click()
        assert browser.is_element_present_by_css(
            "meta[property='og:title'][content*='Lists']"
        )
        assert browser.is_element_present_by_css(
            "meta[property='og:type'][content='website']"
        )
        assert browser.is_element_present_by_css(
            "meta[property='og:image'][content*='openlibrary.org/images']"
        )
        assert browser.is_element_present_by_css(
            "meta[property='og:url'][content*='/lists/']"
        )
        assert browser.is_element_present_by_css(
            "meta[property='og:site_name'][content='Open Library']"
        )
        assert browser.is_element_present_by_css("meta[property='og:description']")
        assert browser.is_element_present_by_css(
            "a[href*='facebook.com/sharer/sharer.php']"
        )
        assert browser.is_element_present_by_css("a[href*='twitter.com/intent/tweet']")
