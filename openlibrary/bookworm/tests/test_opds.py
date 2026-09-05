import json
from pathlib import Path

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


def test_no_cover_field_emitted():
    """Cover URLs are intentionally omitted from import records.

    OL's server-side cover fetch is gated by two host allowlists none of these
    feed hosts satisfy, and the match/merge path (which feed re-imports hit)
    retries a doomed URL 10x with a 2s sleep — up to 20s wasted per record. So
    we don't ship a ``cover`` field; covers are a later, dedicated concern. #12844
    """
    for name, feed in [("bwb", BWB), ("gutenberg", GUTENBERG), ("lenny", LENNY)]:
        for pub in _pubs(name):
            rec = to_import_record(pub, feed)
            assert rec is not None, f"{name}: record should parse"
            assert "cover" not in rec, f"{name}: cover should be omitted"


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
