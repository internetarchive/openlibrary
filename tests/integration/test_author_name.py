import pytest
from splinter import Browser

class TestAuthorName:
    host = 'http://localhost:8080/works'    
    
    @pytest.fixture()
    def browser(self):
        browser = Browser('chrome')
        yield browser
        browser.quit()
        
    def test_author_name_with_dates(self, browser):
        url = self.host + '/OL118420W/Flatland'
        browser.visit(url)
        title = browser.find_by_css(".edition-byline")[0].text
        begin_of_date = title.find('(')
        if begin_of_date:
            begin_of_date+=1
        end_of_date = title.find(')')
        date = title[begin_of_date:end_of_date]
        assert date
        
    def test_author_birth_and_death_year(self, browser):
        url = self.host + '/OL118420W/Flatland'
        browser.visit(url)
        title = browser.find_by_css(".edition-byline")[0].text
        begin_of_date = title.find('(')
        if begin_of_date:
            begin_of_date+=1
        end_of_date = title.find(')')
        date = title[begin_of_date:end_of_date]
        len_if_author_alive = 7
        len_if_author_dead = 11
        assert len(date) == len_if_author_alive or len(date) == len_if_author_dead
        
browser = Browser('chrome')
test = TestAuthorName()
test.test_author_name_with_dates(browser=browser)
test.test_author_birth_and_death_year(browser=browser)
# class TestMicrodata:
#     host = 'http://localhost:8080'

#     @pytest.fixture()
#     def browser(self):
#         browser = Browser('chrome')
#         yield browser
#         browser.quit()

#     def test_open_graph_metadata_on_work(self, browser):
#         url = self.host + '/works/OL6037022W/Remix'
#         browser.visit(url)
#         assert browser.is_element_present_by_css(
#             "#content > div.contentContainer[itemtype='https://schema.org/Book']"
#         )

#     def test_open_graph_metadata_on_edition(self, browser):
#         url = self.host + '/books/OL24218235M/Remix'
#         browser.visit(url)
#         assert browser.is_element_present_by_css(
#             "#contentBody[itemtype='https://schema.org/Book']"
#         )
