"""The task page's lookup links: the field's standing sources, plus the ones the record brings in."""

from types import SimpleNamespace

from openlibrary.contribute.field_guides import build_link_outs, get_field_guides, is_speculative
from openlibrary.plugins.openlibrary import contribute

ISBN = "9780441172719"


def labels(links):
    return [link.label for link in links]


def test_the_standing_sources_open_on_the_isbn():
    links = build_link_outs(get_field_guides()["number_of_pages"], ISBN)
    assert labels(links) == ["Google Books", "WorldCat", "Amazon"]
    assert all(ISBN in link.url for link in links)


def test_science_fiction_and_fantasy_lead_with_isfdb():
    guides = get_field_guides()
    links = build_link_outs(guides["number_of_pages"], ISBN, speculative=True)
    assert labels(links)[0] == "ISFDB"
    assert links[0].url.endswith(f"arg={ISBN}&type=ISBN")
    assert links[0].tip
    # Only the fields ISFDB answers ask for it.
    assert "ISFDB" not in labels(build_link_outs(guides["languages"], ISBN, speculative=True))


def test_subjects_and_genre_names_say_whether_a_work_is_speculative():
    assert is_speculative(["Fiction", "Science Fiction & Fantasy"])
    assert is_speculative(["Fantasy fiction"])
    assert is_speculative(["Fiction, science fiction, general"])
    assert not is_speculative(["Fiction", "Science", "History of science"])


def test_an_lccn_brings_the_record_and_drops_the_catalog_search():
    links = build_link_outs(get_field_guides()["publishers"], ISBN, lccn="99462492", speculative=True)
    assert labels(links) == ["Library of Congress record", "ISFDB", "WorldCat", "Google Books"]
    assert links[0].url == "https://lccn.loc.gov/99462492"
    # Without one, the catalog search stays and leads.
    assert labels(build_link_outs(get_field_guides()["publishers"], ISBN)) == ["Library of Congress", "WorldCat", "Google Books"]
    # A page count isn't read off the record, so the LCCN changes nothing there.
    assert "Library of Congress record" not in labels(build_link_outs(get_field_guides()["number_of_pages"], ISBN, lccn="99462492"))


def test_an_edition_without_an_isbn_gets_title_and_author_searches():
    links = build_link_outs(get_field_guides()["publishers"], None, title="The Dispossessed", authors="Ursula K. Le Guin", speculative=True)
    assert labels(links) == ["ISFDB", "Library of Congress", "WorldCat", "Google Books"]
    assert "The+Dispossessed+Ursula+K.+Le+Guin" in links[2].url
    # ISFDB's title search takes the title alone.
    assert links[0].url.endswith("arg=The+Dispossessed&type=Fiction+Titles")
    assert build_link_outs(get_field_guides()["publishers"], None) == []


def test_contributors_show_with_their_roles():
    edition = {
        "contributors": [SimpleNamespace(get=lambda k, d=None: {"name": "Ken Liu", "role": "Translator"}.get(k, d)), {"name": "Jane Doe"}],
        "contributions": ["Ken Liu (Translator)", "Stephan Martiniere (Cover artist)"],
    }
    assert contribute.format_contributors(edition) == "Ken Liu (Translator), Jane Doe, Stephan Martiniere (Cover artist)"
    assert contribute.format_contributors({}) == ""
