import pytest
from splinter import Browser


class TestMicrodata:
    host = 'http://localhost:8080'

    @pytest.fixture()
    def browser(self):
        browser = Browser('chrome')
        yield browser
        browser.quit()

    def test_open_graph_metadata_on_work(self, browser):
        url = self.host + '/works/OL6037022W/Remix'
        browser.visit(url)
        assert browser.is_element_present_by_css(
            "#content > div.contentContainer[itemtype='https://schema.org/Book']"
        )

    def test_open_graph_metadata_on_edition(self, browser):
        url = self.host + '/books/OL24218235M/Remix'
        browser.visit(url)
        assert browser.is_element_present_by_css(
            "#contentBody[itemtype='https://schema.org/Book']"
        )
