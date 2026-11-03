import pytest

from infogami.utils import macro
from openlibrary.plugins.upstream.table_of_contents import TableOfContents, TocEntry, can_link_to_ia_page


class TestTableOfContents:
    def test_from_db_well_formatted(self):
        db_table_of_contents = [
            {"level": 1, "title": "Chapter 1"},
            {"level": 2, "title": "Section 1.1"},
            {"level": 2, "title": "Section 1.2"},
            {"level": 1, "title": "Chapter 2"},
        ]

        toc = TableOfContents.from_db(db_table_of_contents)

        assert toc.entries == [
            TocEntry(level=1, title="Chapter 1"),
            TocEntry(level=2, title="Section 1.1"),
            TocEntry(level=2, title="Section 1.2"),
            TocEntry(level=1, title="Chapter 2"),
        ]

    def test_from_db_empty(self):
        db_table_of_contents = []

        toc = TableOfContents.from_db(db_table_of_contents)

        assert toc.entries == []

    def test_from_db_string_rows(self):
        db_table_of_contents = [
            "Chapter 1",
            "Section 1.1",
            "Section 1.2",
            "Chapter 2",
        ]

        toc = TableOfContents.from_db(db_table_of_contents)

        assert toc.entries == [
            TocEntry(level=0, title="Chapter 1"),
            TocEntry(level=0, title="Section 1.1"),
            TocEntry(level=0, title="Section 1.2"),
            TocEntry(level=0, title="Chapter 2"),
        ]

    def test_to_db(self):
        toc = TableOfContents(
            [
                TocEntry(level=1, title="Chapter 1"),
                TocEntry(level=2, title="Section 1.1"),
                TocEntry(level=2, title="Section 1.2"),
                TocEntry(level=1, title="Chapter 2"),
            ]
        )

        assert toc.to_db() == [
            {"level": 1, "title": "Chapter 1"},
            {"level": 2, "title": "Section 1.1"},
            {"level": 2, "title": "Section 1.2"},
            {"level": 1, "title": "Chapter 2"},
        ]

    def test_from_db_complex(self):
        db_table_of_contents = [
            {
                "level": 1,
                "title": "Chapter 1",
                "authors": [{"name": "Author 1"}],
                "subtitle": "Subtitle 1",
                "description": "Description 1",
            },
            {"level": 2, "title": "Section 1.1"},
            {"level": 2, "title": "Section 1.2"},
            {"level": 1, "title": "Chapter 2"},
        ]

        toc = TableOfContents.from_db(db_table_of_contents)

        assert toc.entries == [
            TocEntry(
                level=1,
                title="Chapter 1",
                authors=[{"name": "Author 1"}],
                subtitle="Subtitle 1",
                description="Description 1",
            ),
            TocEntry(level=2, title="Section 1.1"),
            TocEntry(level=2, title="Section 1.2"),
            TocEntry(level=1, title="Chapter 2"),
        ]

    def test_from_markdown(self):
        text = """\
            | Chapter 1 | 1
            | Section 1.1 | 2
            | Section 1.2 | 3
        """

        toc = TableOfContents.from_markdown(text)

        assert toc.entries == [
            TocEntry(level=0, title="Chapter 1", pagenum="1"),
            TocEntry(level=0, title="Section 1.1", pagenum="2"),
            TocEntry(level=0, title="Section 1.2", pagenum="3"),
        ]

    def test_from_markdown_empty_lines(self):
        text = """\
            | Chapter 1 | 1

            | Section 1.1 | 2
            | Section 1.2 | 3
        """

        toc = TableOfContents.from_markdown(text)

        assert toc.entries == [
            TocEntry(level=0, title="Chapter 1", pagenum="1"),
            TocEntry(level=0, title="Section 1.1", pagenum="2"),
            TocEntry(level=0, title="Section 1.2", pagenum="3"),
        ]


class TestTocEntry:
    def test_from_dict(self):
        d = {
            "level": 1,
            "label": "Chapter 1",
            "title": "Chapter 1",
            "pagenum": "1",
            "authors": [{"name": "Author 1"}],
            "subtitle": "Subtitle 1",
            "description": "Description 1",
        }

        entry = TocEntry.from_dict(d)

        assert entry == TocEntry(
            level=1,
            label="Chapter 1",
            title="Chapter 1",
            pagenum="1",
            authors=[{"name": "Author 1"}],
            subtitle="Subtitle 1",
            description="Description 1",
        )

    def test_from_dict_missing_fields(self):
        d = {"level": 1}
        entry = TocEntry.from_dict(d)
        assert entry == TocEntry(level=1)

    def test_to_dict(self):
        entry = TocEntry(
            level=1,
            label="Chapter 1",
            title="Chapter 1",
            pagenum="1",
            authors=[{"name": "Author 1"}],
            subtitle="Subtitle 1",
            description="Description 1",
        )

        assert entry.to_dict() == {
            "level": 1,
            "label": "Chapter 1",
            "title": "Chapter 1",
            "pagenum": "1",
            "authors": [{"name": "Author 1"}],
            "subtitle": "Subtitle 1",
            "description": "Description 1",
        }

    def test_to_dict_missing_fields(self):
        entry = TocEntry(level=1)
        assert entry.to_dict() == {"level": 1}

        entry = TocEntry(level=1, title="")
        assert entry.to_dict() == {"level": 1, "title": ""}

    def test_from_markdown(self):
        line = "| Chapter 1 | 1"
        entry = TocEntry.from_markdown(line)
        assert entry == TocEntry(level=0, title="Chapter 1", pagenum="1")

        line = " ** | Chapter 1 | 1"
        entry = TocEntry.from_markdown(line)
        assert entry == TocEntry(level=2, title="Chapter 1", pagenum="1")

        line = "Chapter missing pipe"
        entry = TocEntry.from_markdown(line)
        assert entry == TocEntry(level=0, title="Chapter missing pipe")

        line = ' | Just title |  | {"authors": [{"name": "Author 1"}]}'
        entry = TocEntry.from_markdown(line)
        assert entry == TocEntry(level=0, title="Just title", authors=[{"name": "Author 1"}])

    def test_to_markdown(self):
        entry = TocEntry(level=0, title="Chapter 1", pagenum="1")
        assert entry.to_markdown() == " | Chapter 1 | 1"

        entry = TocEntry(level=2, title="Chapter 1", pagenum="1")
        assert entry.to_markdown() == "** | Chapter 1 | 1"

        entry = TocEntry(level=0, title="Just title")
        assert entry.to_markdown() == " | Just title | "

        entry = TocEntry(level=0, title="", authors=[{"name": "Author 1"}])
        assert entry.to_markdown() == ' |  |  | {"authors": [{"name": "Author 1"}]}'

    def test_from_markdown_regex_edge_cases(self):
        r"""Test that the regex pattern handles various edge cases correctly.

        The regex pattern r"(\**)(.*)" always matches any string, but we want
        to ensure the parsing logic handles different formats correctly.
        """
        # Empty string - regex matches with empty groups
        entry = TocEntry.from_markdown("")
        assert entry == TocEntry(level=0, title=None)

        # Only asterisks - asterisks become level, empty text becomes None title
        entry = TocEntry.from_markdown("***")
        assert entry == TocEntry(level=3, title=None)

        # Whitespace variations
        entry = TocEntry.from_markdown("  | Title  ")
        assert entry == TocEntry(level=0, title="Title", label=None)

        # Many asterisks with pipe
        entry = TocEntry.from_markdown("*****|Chapter | 10")
        assert entry == TocEntry(level=5, title="Chapter", pagenum="10")

        # Asterisks with text and pipe - asterisks become level, rest is parsed normally
        entry = TocEntry.from_markdown("***Chapter| 5")
        assert entry == TocEntry(level=3, label="Chapter", title="5", pagenum=None)

        # Special characters in title
        entry = TocEntry.from_markdown("| Chapter (2nd edition) | 15")
        assert entry == TocEntry(level=0, title="Chapter (2nd edition)", pagenum="15")

        # Extra asterisks with label and title
        entry = TocEntry.from_markdown("**Chapter 1|Title of Chapter|5")
        assert entry == TocEntry(level=2, title="Title of Chapter", label="Chapter 1", pagenum="5")


class TestCanLinkToIaPage:
    @pytest.mark.parametrize("pagenum", ["1", "11", "250", "n0", "n11"])
    def test_page_and_scan_numbers_can_link(self, pagenum):
        assert can_link_to_ia_page(pagenum)

    @pytest.mark.parametrize("pagenum", [None, "", "n", "xi", "11a", "n11a", "11-12"])
    def test_other_values_cannot_link(self, pagenum):
        assert not can_link_to_ia_page(pagenum)

    def test_toc_macro_links_scan_numbers(self, render_template):
        macro.load_macros("openlibrary", lazy=True)
        toc = TableOfContents.from_markdown("| Chapter one | n11\n| Chapter two | 23\n| Preface | xi")
        html = str(macro.macrostore["TableOfContents"](toc, ocaid="behnd_the_mask"))

        assert 'href="//archive.org/details/behnd_the_mask/page/n11"' in html
        assert 'href="//archive.org/details/behnd_the_mask/page/23"' in html
        assert "/page/xi" not in html
