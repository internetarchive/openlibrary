"""``parse_identifier`` routing for the OPDS and RDF import parsers.

Both modules carry a byte-identical copy of ``parse_identifier``, so every case
here runs against both. Only the OPDS copy is reachable today -- ``import_rdf``
never registers it in its ``parser_map`` -- but the two are kept in step.

These exercise ``parse_identifier`` directly rather than through ``parse()``,
because ``parse()`` builds an ``import_edition_builder()`` with no arguments and
that validates the still-empty record, so it raises before any element is read.
That is a separate defect from the field routing tested here.
"""

from xml.etree import ElementTree as ET

import pytest

from openlibrary.plugins.importapi import import_opds, import_rdf

IDENTIFIER_TAG = "{http://purl.org/dc/terms/}identifier"


@pytest.fixture(params=[import_opds, import_rdf], ids=["opds", "rdf"])
def parse_identifier(request):
    return request.param.parse_identifier


def identifier_element(text: str) -> ET.Element:
    element = ET.Element(IDENTIFIER_TAG)
    element.text = text
    return element


@pytest.mark.parametrize(
    ("identifier", "expected"),
    [
        # A hyphenated ISBN 10 is 13 characters long, so counting the raw string
        # files it as an ISBN 13. It is the field that has to follow the
        # canonical form.
        ("urn:ISBN:0-486-28061-6", ("isbn_10", "0486280616")),
        ("urn:ISBN:978-0-486-28061-5", ("isbn_13", "9780486280615")),
        ("urn:ISBN:0486280616", ("isbn_10", "0486280616")),
        ("urn:ISBN:9780486280615", ("isbn_13", "9780486280615")),
        # Spacing and a lowercase check digit are canonicalized too.
        ("urn:ISBN:184115186x", ("isbn_10", "184115186X")),
        ("urn:ISBN:123-456-789-X ", ("isbn_10", "123456789X")),
    ],
)
def test_isbn_is_routed_by_canonical_form(parse_identifier, identifier, expected):
    assert parse_identifier(identifier_element(identifier), "identifier") == expected


@pytest.mark.parametrize(
    "identifier",
    [
        # Each of these used to fall off the end of the function and return a
        # bare None, which the caller unpacks -- a TypeError, so a 500.
        "urn:ISBN:",
        "urn:ISBN:abc",
        "urn:ISBN:12345678901234",
        "urn:ISBN:97804862806",
    ],
)
def test_unusable_isbn_returns_a_pair_rather_than_none(parse_identifier, identifier):
    assert parse_identifier(identifier_element(identifier), "identifier") == (None, None)


def test_ocaid_is_unchanged(parse_identifier):
    element = identifier_element("http://www.archive.org/details/someocaid")
    assert parse_identifier(element, "identifier") == ("ocaid", "someocaid")


def test_unknown_identifier_scheme_is_ignored(parse_identifier):
    element = identifier_element("urn:uuid:7c2cbf1e-0e2a-4f6a-9f0f-2f4b0a9d1a11")
    assert parse_identifier(element, "identifier") == (None, None)


def test_the_caller_can_always_unpack_the_result(parse_identifier):
    """``parse()`` does ``new_key, val = parser_map[e.tag][1](e, key)``.

    Every branch must therefore yield a pair. The ISBN branch used to fall off
    the end of the function and return a bare None for any length but 10 or 13,
    which is the TypeError behind the 500.
    """
    for identifier in ("urn:ISBN:0-486-28061-6", "urn:ISBN:", "urn:ISBN:junk", "http://www.archive.org/details/x", "other"):
        result = parse_identifier(identifier_element(identifier), "identifier")
        assert isinstance(result, tuple), f"{identifier} returned {result!r}, which the caller cannot unpack"
        assert len(result) == 2
