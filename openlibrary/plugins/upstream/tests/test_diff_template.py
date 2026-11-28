"""Tests for the revision diff page (templates/diff.html)."""

import web

from openlibrary.mocks.mock_infobase import MockSite


def make_site() -> MockSite:
    site = MockSite()
    # find_diff() reads each property's expected type from the work's type.
    site.save({"key": "/type/link", "type": {"key": "/type/type"}})
    site.save(
        {
            "key": "/type/work",
            "type": {"key": "/type/type"},
            "properties": [
                {"name": "title", "expected_type": {"key": "/type/string"}},
                {"name": "links", "expected_type": {"key": "/type/link"}},
            ],
        }
    )
    return site


def make_work(site: MockSite, revision: int, links: list[tuple[str, str]]):
    return site.new(
        "/works/OL1W",
        {
            "key": "/works/OL1W",
            "type": {"key": "/type/work"},
            "title": "A Work",
            "revision": revision,
            "links": [{"url": url, "title": title, "type": {"key": "/type/link"}} for url, title in links],
        },
    )


class TestDiffTemplate:
    def render(self, render_template, a, b):
        web.template.Template.globals["get_version"] = lambda key, revision: None
        return render_template("diff", a, b, show_header=False)

    def test_changed_link_is_shown(self, render_template):
        """Changing a link's URL and title is a difference (#3414).

        Links are embedded objects without a key, and Thing equality compares keys,
        so two lists of links with the same length used to compare equal.
        """
        site = make_site()
        a = make_work(site, 1, [("https://example.com/old", "Old link")])
        b = make_work(site, 2, [("https://example.com/new", "New link")])

        html = self.render(render_template, a, b)

        assert "Both the revisions are identical." not in html
        assert "https://example.com/old" in html
        assert "https://example.com/new" in html

    def test_identical_revisions(self, render_template):
        site = make_site()
        a = make_work(site, 1, [("https://example.com/same", "Same link")])
        b = make_work(site, 2, [("https://example.com/same", "Same link")])

        html = self.render(render_template, a, b)

        assert "Both the revisions are identical." in html
