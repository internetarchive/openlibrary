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
            begin_of_date += 1
        end_of_date = title.find(')')
        date = title[begin_of_date:end_of_date]
        assert date

    def test_author_birth_and_death_year(self, browser):
        url = self.host + '/OL118420W/Flatland'
        browser.visit(url)
        title = browser.find_by_css(".edition-byline")[0].text
        begin_of_date = title.find('(')
        if begin_of_date:
            begin_of_date += 1
        end_of_date = title.find(')')
        date = title[begin_of_date:end_of_date]
        len_if_author_alive = 7
        len_if_author_dead = 11
        assert len(date) == len_if_author_alive or len(date) == len_if_author_dead

    def test_all_author_birth_and_death_year(self, browser):
        url = self.host + '/OL5702375W/Three_cups_of_tea'
        browser.visit(url)
        title = browser.find_by_css(".edition-byline")[0].text
        title_length = len(title)
        author_dates = []
        authors_quantity = title.count('(')
        for i in range(0, authors_quantity):
            if author_dates != []:
                title = title[end_of_date + 1 : title_length]
            begin_of_date = title.find('(')
            if begin_of_date:
                begin_of_date += 1
            else:
                break
            end_of_date = title.find(')')
            date = title[begin_of_date:end_of_date]
            author_dates.append(date)
        len_if_no_birth_data = 3
        len_if_author_alive = 7
        len_if_author_dead = 11
        for date in author_dates:
            assert (
                len(date) == len_if_no_birth_data
                or len(date) == len_if_author_alive
                or len(date) == len_if_author_dead
            )

    def test_all_works_from_author(self, browser):
        url = 'http://localhost:8080/authors/OL18319A/Mark_Twain'
        browser.visit(url)
        error = browser.find_by_css(".error")
        if error:
            raise Exception("Error in page")
        titles = browser.find_by_css(".bookauthor")
        for title_driver in titles:
            title = title_driver.text
            title_length = len(title)
            author_dates = []
            authors_quantity = title.count('(')
            for i in range(0, authors_quantity):
                if author_dates != []:
                    title = title[end_of_date + 1 : title_length]
                begin_of_date = title.find('(')
                if begin_of_date:
                    begin_of_date += 1
                else:
                    break
                end_of_date = title.find(')')
                date = title[begin_of_date:end_of_date]
                author_dates.append(date)
            len_if_no_birth_data = 3
            len_if_author_alive = 7
            len_if_author_dead = 11
            for date in author_dates:
                assert (
                    len(date) == len_if_no_birth_data
                    or len(date) == len_if_author_alive
                    or len(date) == len_if_author_dead
                )
