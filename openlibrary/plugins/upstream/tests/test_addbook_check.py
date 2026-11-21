"""books/check.html: the possible-matches page re-posts the add form."""

import pytest
import web
from bs4 import BeautifulSoup


class TestCheckTemplate:
    @pytest.fixture(autouse=True)
    def lang(self, request_context_fixture):
        request_context_fixture(lang="en")

    def render(self, render_template, recaptcha=None):
        d = web.storage(
            title="Moby Dick",
            publisher="Harper",
            publish_date="1851",
            id_name="isbn_13",
            id_value="9780000000000",
            web_book_url="https://example.com/moby",
            authors=[],
            author_names=["Herman Melville"],
        )
        matches = [web.storage(key="/works/OL1W", title="Moby Dick", cover_url="", authors=[], edition_count=2, first_publish_year=1851)]
        return BeautifulSoup(str(render_template("books/check", d, matches, recaptcha=recaptcha)), "lxml")

    def test_reposts_every_add_field(self, render_template):
        form = self.render(render_template).find("form", id="addbook")
        fields = {el["name"]: el["value"] for el in form.find_all("input")}
        assert fields["book_title"] == "Moby Dick"
        assert fields["web_book_url"] == "https://example.com/moby"
        assert "title" not in fields

    def test_without_captcha_the_form_stays_hidden(self, render_template):
        form = self.render(render_template).find("form", id="addbook")
        assert "hidden" in form["class"]
        assert form.find(class_="g-recaptcha") is None

    def test_captcha_renders_inside_the_form_above_the_matches(self, render_template):
        soup = self.render(render_template, recaptcha=web.storage(public_key="pk"))
        form = soup.find("form", id="addbook")
        assert "hidden" not in form["class"]
        assert form.find(class_="g-recaptcha")["data-sitekey"] == "pk"
        assert form.find(id="recaptcha-needed") is not None
        assert form.find_next(id="searchResults") is not None
