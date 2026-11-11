import json
from pathlib import Path

import pytest

from openlibrary.bookworm.opds import Feed, Link, Publication, extract_local_id, to_import_record

SAMPLES = Path(__file__).parent / "samples"

BWB = Feed(provider_name="betterworldbooks", id_strategy="isbn")
GUTENBERG = Feed(provider_name="project_gutenberg", id_strategy="gutenberg")
LENNY = Feed(provider_name="lenny", id_strategy="self_link")


def _pubs(name: str) -> list[Publication]:
    return [Publication(**p) for p in json.loads((SAMPLES / f"{name}.json").read_text())]


def test_bwb_record_and_buy_acquisition():
    rec = to_import_record(_pubs("bwb")[0], BWB)
    assert rec["isbn_13"] == ["9781737408802"]
    assert rec["source_records"] == ["betterworldbooks:9781737408802"]
    assert rec["title"].startswith("The Brick House")
    assert rec["authors"][0]["name"]
    acq = rec["acquisitions"]
    assert len(acq) == 1
    assert acq[0]["provider_name"] == "betterworldbooks"
    assert acq[0]["local_id"] == "9781737408802"
    assert acq[0]["data"]["access"] == "buy"
    assert acq[0]["data"]["price"] == {"currency": "USD", "value": 1.25}


def test_gutenberg_record_and_open_access():
    rec = to_import_record(_pubs("gutenberg")[0], GUTENBERG)
    # id comes from the gutenberg.org/ebooks/<id> URL, not an ISBN
    assert rec["identifiers"] == {"project_gutenberg": ["67979"]}
    assert rec["source_records"] == ["project_gutenberg:67979"]
    assert rec["title"] == "The Blue Castle: a novel"
    assert rec["authors"] == [{"name": "Montgomery, L. M. (Lucy Maud)"}]  # author was a dict, normalized
    acq = rec["acquisitions"][0]
    assert acq["data"]["access"] == "open-access"
    assert acq["data"]["url"].endswith(".epub")
    assert acq["data"]["format"] == "application/epub+zip"
    assert "price" not in acq["data"]  # free


def test_lenny_id_from_self_link():
    rec = to_import_record(_pubs("lenny")[0], LENNY)
    # Lenny has no metadata.identifier -> id from the self link's last segment
    assert rec["identifiers"] == {"lenny": ["37044775"]}
    assert rec["source_records"] == ["lenny:37044775"]
    assert rec["title"] == "Flatland"
    assert rec["authors"] == [{"name": "Edwin Abbott Abbott"}]
    assert rec["languages"] == ["eng"]  # ISO "en" normalized to MARC21
    acq = rec["acquisitions"][0]
    assert acq["data"]["access"] == "open-access"
    assert acq["local_id"] == "37044775"


def test_all_three_feeds_map_every_sample_publication():
    # The whole point: no publication silently dropped across the 3 real feeds.
    for name, feed in [("bwb", BWB), ("gutenberg", GUTENBERG), ("lenny", LENNY)]:
        pubs = _pubs(name)
        records = [to_import_record(p, feed) for p in pubs]
        assert all(r is not None for r in records), f"{name}: some publications failed to map"
        assert all(r["acquisitions"] for r in records), f"{name}: missing acquisitions"


def test_skips_publication_without_title_or_authors():
    pub = Publication(metadata={"identifier": "urn:isbn:9781737408802"}, links=[])
    assert to_import_record(pub, BWB) is None


def test_self_link_id_strips_query_and_fragment():
    pub = Publication(metadata={"title": "X"}, links=[Link(rel="self", href="https://lenny/v1/api/opds/pub/37044775?format=json#frag")])
    assert extract_local_id(pub, LENNY) == "37044775"


@pytest.mark.parametrize(
    ("name", "feed", "expected_cover"),
    [
        ("gutenberg", GUTENBERG, "https://www.gutenberg.org/cache/epub/67979/pg67979.cover.medium.jpg"),
        ("lenny", LENNY, "https://covers.openlibrary.org/b/id/12622094-L.jpg"),
        # Not on coverstore's allowlist, so omitted rather than left for
        # add_cover() to retry.
        ("bwb", BWB, None),
    ],
)
def test_cover_emitted_only_when_coverstore_allows_it(name, feed, expected_cover):
    rec = to_import_record(_pubs(name)[0], feed)
    assert rec is not None
    assert rec.get("cover") == expected_cover


def test_lenny_borrow_acquisition_is_not_discarded():
    """A borrowable Lenny publication must import with its acquisition.

    Only `buy` and `open-access` were mapped, so a publication whose only
    acquisition link was `acquisition/borrow` produced an import record with no
    `acquisitions` at all — measured at 70 of 95 publications on
    lennyforlibraries.org (2026-09-04). Nothing downstream can render what was
    never imported. See #13552.

    The sample is a real publication captured from the live feed.
    """
    rec = to_import_record(_pubs("lenny_borrow")[0], LENNY)
    assert rec is not None, "a borrowable publication produced no import record"
    acq = rec["acquisitions"]
    assert len(acq) == 1, f"expected one acquisition, got {acq}"
    assert acq[0]["provider_name"] == "lenny"
    assert acq[0]["data"]["access"] == "borrow"
    assert acq[0]["data"]["url"].endswith("/borrow")


def test_lenny_borrow_keeps_availability_and_auth_document():
    """`properties.availability` says whether the book can be borrowed right
    now, and `properties.authenticate` points at the provider's OPDS
    Authentication Document — where a patron is sent to log in. Both are needed
    for a borrow CTA, and both would be lost if only the flat fields were kept.
    """
    rec = to_import_record(_pubs("lenny_borrow")[0], LENNY)
    data = rec["acquisitions"][0]["data"]
    assert data["availability"] == "available"
    props = data["link"]["properties"]
    assert props["authenticate"]["href"].endswith("/oauth/implicit")


def test_borrow_rel_is_recognised_as_an_acquisition_link():
    pub = Publication(
        links=[
            Link(rel="http://opds-spec.org/acquisition/borrow", href="https://x/borrow"),
            Link(rel="self", href="https://x/opds/1"),
        ]
    )
    assert [link.rel for link in pub.acquisition_links()] == ["http://opds-spec.org/acquisition/borrow"]


@pytest.mark.parametrize(
    ("flag", "local_id", "expected"),
    [
        (True, "51008637", "OL51008637M"),
        (False, "51008637", None),
        (True, "not-a-number", None),
    ],
)
def test_names_the_ol_edition_only_when_the_feed_says_so(flag, local_id, expected):
    """``local_id_is_ol_edition`` is what makes a record name its edition.

    Without it the record carries only a title and a provider id, and the
    catalog is left to infer the edition from the title -- against every
    same-title edition in the catalog. With it the record answers outright.
    Guarded on the id being numeric, since ``OL<not-a-number>M`` is not a key.
    """
    feed = Feed(provider_name="lenny", id_strategy="self_link", local_id_is_ol_edition=flag)
    pub = Publication(
        metadata={"title": "The Art of War", "author": {"name": "Sun Tzu"}},
        links=[{"rel": "self", "href": f"https://example.org/opds/{local_id}"}],
    )
    record = to_import_record(pub, feed)
    assert record is not None
    assert record.get("openlibrary") == expected


def test_acquisitions_keep_the_source_publication_link():
    """The publication's own ``self`` link must survive ingestion.

    ``extract_local_id`` already reads this link for the ``self_link`` id
    strategy and drops the URL once it has the id. Without it a consumer
    cannot follow an acquisition back to the provider's own record for the
    book, and has to reverse-engineer that URL per provider -- done for Better
    World Books, and not something that scales as feeds are onboarded.
    """
    for name, feed in [("bwb", BWB), ("gutenberg", GUTENBERG), ("lenny", LENNY)]:
        pub = _pubs(name)[0]
        rec = to_import_record(pub, feed)
        assert rec["acquisitions"], name
        for acq in rec["acquisitions"]:
            assert acq["data"]["source_url"] == pub.self_href(), name


def test_the_source_link_is_the_publication_not_the_acquisition():
    """Two different URLs.

    A test that only asserted the key was present would also pass against
    ``data["source_url"] = link.href``, which carries nothing new.
    """
    pub = _pubs("gutenberg")[0]
    acq = to_import_record(pub, GUTENBERG)["acquisitions"][0]
    assert acq["data"]["source_url"] != acq["data"]["url"]


def test_source_url_is_absent_when_the_feed_gives_no_self_link():
    """Absent rather than empty: a key holding "" reads as a real location."""
    pub = Publication(
        metadata={"title": "A Book", "author": "Someone", "identifier": "urn:isbn:9781737408802"},
        links=[Link(rel="http://opds-spec.org/acquisition/buy", href="https://example.test/buy/1", type="text/html")],
    )
    rec = to_import_record(pub, BWB)
    assert rec is not None
    assert "source_url" not in rec["acquisitions"][0]["data"]


def test_gutenberg_descriptive_metadata():
    pub = Publication(**json.loads((SAMPLES / "gutenberg_2641.json").read_text()))
    rec = to_import_record(pub, GUTENBERG)

    assert rec["description"].startswith("Creators: E. M. Forster")
    # Bookshelves and LCSH-style headings are topics; the LCC entry is not.
    assert "Novels" in rec["subjects"]
    assert "Florence (Italy) -- Fiction" in rec["subjects"]
    assert not any("PR" in s for s in rec["subjects"])
    assert rec["lc_classifications"] == ["PR"]


def test_lenny_descriptive_metadata():
    rec = to_import_record(_pubs("lenny")[0], LENNY)
    assert rec["description"].startswith("<p><i>Flatland</i>")
    assert rec["number_of_pages"] == 110


def test_metadata_field_shapes():
    """OPDS allows a bare string, a language map, an object, or a list of these."""
    pub = Publication(
        metadata={
            "title": "X",
            "author": "Jane Doe",
            "subtitle": {"fr": "Un sous-titre", "en": "A subtitle"},
            "description": {"en": " Described. "},
            "publisher": {"name": "Some Press"},
            "subject": ["Cats", {"name": {"en": "Dogs"}, "scheme": "https://example.org/"}, "Cats"],
            "numberOfPages": "12",
        },
        links=[Link(rel="self", href="https://lenny/v1/api/opds/pub/1")],
    )
    rec = to_import_record(pub, LENNY)

    assert rec["authors"] == [{"name": "Jane Doe"}]
    assert rec["subtitle"] == "A subtitle"
    assert rec["description"] == "Described."
    assert rec["publishers"] == ["Some Press"]
    assert rec["subjects"] == ["Cats", "Dogs"]
    assert "number_of_pages" not in rec  # not an integer


def test_absent_metadata_adds_no_fields():
    rec = to_import_record(_pubs("bwb")[0], BWB)
    for field in ("subtitle", "description", "subjects", "lc_classifications", "number_of_pages"):
        assert field not in rec


def test_gutenberg_author_id_becomes_remote_id():
    pub = Publication(**json.loads((SAMPLES / "gutenberg_2641.json").read_text()))
    assert to_import_record(pub, GUTENBERG)["authors"] == [
        {"name": "Forster, E. M. (Edward Morgan)", "remote_ids": {"project_gutenberg": "975"}},
    ]


@pytest.mark.parametrize("identifier", [None, "https://example.org/authors/975", "https://www.gutenberg.org/ebooks/975"])
def test_unrecognised_author_identifiers_are_ignored(identifier):
    pub = Publication(
        metadata={"title": "X", "author": {"name": "Jane Doe", "identifier": identifier}},
        links=[Link(rel="self", href="https://lenny/v1/api/opds/pub/1")],
    )
    assert to_import_record(pub, LENNY)["authors"] == [{"name": "Jane Doe"}]
