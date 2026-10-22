import json
from collections.abc import Iterable
from pathlib import Path

import lxml.etree
import pytest
from lxml import etree

from openlibrary.catalog.marc.marc_binary import MarcBinary
from openlibrary.catalog.marc.marc_xml import DataField, MarcXml
from openlibrary.catalog.marc.parse import (
    NoTitle,
    SeeAlsoAsTitle,
    read_author_person,
    read_description,
    read_edition,
)

collection_tag = "{http://www.loc.gov/MARC21/slim}collection"
record_tag = "{http://www.loc.gov/MARC21/slim}record"

xml_samples = [
    "39002054008678_yale_edu",
    "flatlandromanceo00abbouoft",
    "nybc200247",
    "secretcodeofsucc00stjo",
    "warofrebellionco1473unit",
    "zweibchersatir01horauoft",
    "onquietcomedyint00brid",
    "00schlgoog",
    "0descriptionofta1682unit",
    "1733mmoiresdel00vill",
    "13dipolarcycload00burk",
    "bijouorannualofl1828cole",
    "soilsurveyrepor00statgoog",
    "cu31924091184469",  # MARC XML collection record
    "engineercorpsofh00sher",
]

bin_samples = [
    "bijouorannualofl1828cole_meta.mrc",
    "onquietcomedyint00brid_meta.mrc",  # LCCN with leading characters
    "merchantsfromcat00ben_meta.mrc",
    "memoirsofjosephf00fouc_meta.mrc",  # MARC8 encoded with e-acute
    "equalsign_title.mrc",  # Title ending in '='
    "bpl_0486266893.mrc",
    "flatlandromanceo00abbouoft_meta.mrc",
    "histoirereligieu05cr_meta.mrc",
    "ithaca_college_75002321.mrc",
    "lc_0444897283.mrc",
    "lc_1416500308.mrc",
    "lesnoirsetlesrou0000garl_meta.mrc",
    "ocm00400866.mrc",
    "secretcodeofsucc00stjo_meta.mrc",
    "uoft_4351105_1626.mrc",
    "warofrebellionco1473unit_meta.mrc",
    "wrapped_lines.mrc",
    "wwu_51323556.mrc",
    "zweibchersatir01horauoft_meta.mrc",
    "talis_two_authors.mrc",
    "talis_no_title.mrc",
    "talis_740.mrc",
    "talis_245p.mrc",
    "talis_856.mrc",
    "talis_multi_work_tiles.mrc",
    "talis_empty_245.mrc",
    "ithaca_two_856u.mrc",
    "collingswood_bad_008.mrc",
    "collingswood_520aa.mrc",
    "upei_short_008.mrc",
    "diebrokeradical400poll_meta.mrc",
    "cu31924091184469_meta.mrc",
    "engineercorpsofh00sher_meta.mrc",
    "henrywardbeecher00robauoft_meta.mrc",
    "thewilliamsrecord_vol29b_meta.mrc",
    "13dipolarcycload00burk_meta.mrc",
    "710_org_name_in_direct_order.mrc",
    "830_series.mrc",
    "880_alternate_script.mrc",
    "880_table_of_contents.mrc",
    "880_Nihon_no_chasho.mrc",
    "880_publisher_unlinked.mrc",
    "880_arabic_french_many_linkages.mrc",
    "test-publish-sn-sl.mrc",
    "test-publish-sn-sl-nd.mrc",
]

date_tests = [  # MARC, expected publish_date
    ("9999_sd_dates.mrc", "[n.d.]"),
    ("reprint_date_wrong_order.mrc", "2010"),
    ("9999_with_correct_date_in_260.mrc", "2003"),
]

TEST_DATA = Path(__file__).with_name("test_data")


class TestParseMARCXML:
    @pytest.mark.parametrize("i", xml_samples)
    def test_xml(self, i):
        expect_filepath = (TEST_DATA / "xml_expect" / i).with_suffix(".json")
        filepath = TEST_DATA / "xml_input" / f"{i}_marc.xml"
        element = etree.parse(filepath, parser=lxml.etree.XMLParser(resolve_entities=False)).getroot()
        # Handle MARC XML collection elements in our test_data expectations:
        if element.tag == collection_tag and element[0].tag == record_tag:
            element = element[0]
        rec = MarcXml(element)
        edition_marc_xml = read_edition(rec)
        assert edition_marc_xml
        j = json.load(expect_filepath.open())
        assert j, f"Unable to open test data: {expect_filepath}"
        msg = f"Processed MARCXML values do not match expectations in {expect_filepath}."
        assert sorted(edition_marc_xml) == sorted(j), msg
        msg += " Key: "
        for key, value in edition_marc_xml.items():
            if isinstance(value, Iterable):  # can not sort a list of dicts
                assert len(value) == len(j[key]), msg + key
                for item in j[key]:
                    assert item in value, msg + key
            else:
                assert value == j[key], msg + key


class TestParseMARCBinary:
    @pytest.mark.parametrize("i", bin_samples)
    def test_binary(self, i):
        expect_filepath = (TEST_DATA / "bin_expect" / i).with_suffix(".json")
        filepath = TEST_DATA / "bin_input" / i
        rec = MarcBinary(filepath.read_bytes())
        edition_marc_bin = read_edition(rec)
        assert edition_marc_bin
        if not Path(expect_filepath).is_file():
            # Missing test expectations file. Create a template from the input, but fail the current test.
            data = json.dumps(edition_marc_bin, indent=2)
            pytest.fail(f"Expectations file {expect_filepath} not found: Please review and commit this JSON:\n{data}")
        j = json.load(expect_filepath.open())
        assert j, f"Unable to open test data: {expect_filepath}"
        msg = f"Processed binary MARC values do not match expectations in {expect_filepath}"
        assert sorted(edition_marc_bin) == sorted(j), msg
        for key, value in edition_marc_bin.items():
            if isinstance(value, Iterable):  # can not sort a list of dicts
                assert len(value) == len(j[key]), msg
                for item in j[key]:
                    assert item in value, f"{msg}. Key: {key}"
            else:
                assert value == j[key], msg

    def test_raises_see_also(self):
        filepath = TEST_DATA / "bin_input" / "talis_see_also.mrc"
        rec = MarcBinary(filepath.read_bytes())
        with pytest.raises(SeeAlsoAsTitle):
            read_edition(rec)

    def test_raises_no_title(self):
        filepath = TEST_DATA / "bin_input" / "talis_no_title2.mrc"
        rec = MarcBinary(filepath.read_bytes())
        with pytest.raises(NoTitle):
            read_edition(rec)

    @pytest.mark.parametrize(("marcfile", "expect"), date_tests)
    def test_dates(self, marcfile, expect):
        filepath = TEST_DATA / "bin_input" / marcfile
        rec = MarcBinary(filepath.read_bytes())
        edition = read_edition(rec)
        assert edition["publish_date"] == expect


class TestParse:
    def test_read_author_person(self):
        xml_author = """
        <datafield xmlns="http://www.loc.gov/MARC21/slim" tag="100" ind1="1" ind2="0">
          <subfield code="a">Rein, Wilhelm,</subfield>
          <subfield code="d">1809-1865.</subfield>
          <subfield code="0">(uri) http://id.loc.gov/authorities/names/no2003007242</subfield>
          <subfield code="0">(uri) http://viaf.org/viaf/sourceID/LC|no2003007242</subfield>
        </datafield>"""
        test_field = DataField(
            None,
            etree.fromstring(xml_author, parser=lxml.etree.XMLParser(resolve_entities=False)),
        )
        result = read_author_person(test_field)

        # Name order remains unchanged from MARC order
        assert result["name"] == "Rein, Wilhelm"
        assert result["birth_date"] == "1809"
        assert result["death_date"] == "1865"
        assert result["entity_type"] == "person"
        assert result["remote_ids"] == {"lc_naf": "no2003007242"}

    def test_read_author_person_title_subfield_not_in_name(self):
        """$c is kept out of `name` so the name can still be flipped and matched (#13853)."""
        xml_author = """
        <datafield xmlns="http://www.loc.gov/MARC21/slim" tag="700" ind1="1" ind2=" ">
          <subfield code="a">France, Anatole,</subfield>
          <subfield code="c">pseud.</subfield>
          <subfield code="d">1844-1924.</subfield>
        </datafield>"""
        test_field = DataField(
            None,
            etree.fromstring(xml_author, parser=lxml.etree.XMLParser(resolve_entities=False)),
        )
        result = read_author_person(test_field, tag="700")

        assert result["name"] == "France, Anatole"
        assert result["title"] == "pseud"
        # `name` now equals $a, so the DRY check drops personal_name. Keeping it
        # would make do_flip() bail out and leave the name in MARC order.
        assert "personal_name" not in result
        assert result["birth_date"] == "1844"
        assert result["death_date"] == "1924"

    def test_read_author_person_title_subfield_only(self):
        """A field with $c and no $a still gets a name from $c."""
        xml_author = """
        <datafield xmlns="http://www.loc.gov/MARC21/slim" tag="700" ind1="0" ind2=" ">
          <subfield code="c">Mother Teresa.</subfield>
        </datafield>"""
        test_field = DataField(
            None,
            etree.fromstring(xml_author, parser=lxml.etree.XMLParser(resolve_entities=False)),
        )
        result = read_author_person(test_field, tag="700")

        assert result["name"] == "Mother Teresa"
        assert result["title"] == "Mother Teresa"


def marc_520(datafields: str) -> MarcXml:
    xml = f"""
    <record xmlns="http://www.loc.gov/MARC21/slim">
      <leader>00000cam a2200000 a 4500</leader>
      {datafields}
    </record>"""
    return MarcXml(etree.fromstring(xml, parser=lxml.etree.XMLParser(resolve_entities=False)))


class TestReadDescription:
    @pytest.mark.parametrize(
        ("summary", "expect"),
        [
            # The ISBD "--" in $a introduces the source, so it folds into the join.
            (
                '...which one of them is a killer?"--',
                '...which one of them is a killer?"--Provided by publisher.',
            ),
            # A record without its own "--" gets the same separator.
            (
                "A summary with no dashes.",
                "A summary with no dashes.--Provided by publisher.",
            ),
            # A "--" in the middle of the text is left alone.
            (
                "Volume one -- volume two.--",
                "Volume one -- volume two.--Provided by publisher.",
            ),
        ],
    )
    def test_source_joined_with_isbd_dashes(self, summary, expect):
        rec = marc_520(
            f"""
            <datafield tag="520" ind1=" " ind2=" ">
              <subfield code="a">{summary}</subfield>
              <subfield code="c">Provided by publisher.</subfield>
            </datafield>"""
        )
        assert read_description(rec) == expect

    @pytest.mark.parametrize(
        ("summary", "expect"),
        [
            ('...caught in its widening gyre" --', '...caught in its widening gyre"'),
            ("...in the author's own words'-- ", "...in the author's own words'"),
            ("A summary with no source.", "A summary with no source."),
        ],
    )
    def test_trailing_dashes_stripped_without_source(self, summary, expect):
        rec = marc_520(
            f"""
            <datafield tag="520" ind1=" " ind2=" ">
              <subfield code="a">{summary}</subfield>
            </datafield>"""
        )
        assert read_description(rec) == expect

    def test_expansion_follows_summary(self):
        rec = marc_520(
            """
            <datafield tag="520" ind1="3" ind2=" ">
              <subfield code="a">A short abstract.</subfield>
              <subfield code="b">A much longer expansion of the abstract.</subfield>
            </datafield>"""
        )
        assert read_description(rec) == "Abstract: A short abstract. A much longer expansion of the abstract."

    @pytest.mark.parametrize(
        ("ind1", "expect"),
        [
            (" ", "The note."),  # Summary is the default and takes no label
            ("8", "The note."),  # 8 generates no display constant
            ("0", "Subject: The note."),
            ("1", "Review: The note."),
            ("2", "Scope and content: The note."),
            ("3", "Abstract: The note."),
            ("4", "Content advice: The note."),
        ],
    )
    def test_first_indicator_labels(self, ind1, expect):
        rec = marc_520(
            f"""
            <datafield tag="520" ind1="{ind1}" ind2=" ">
              <subfield code="a">The note.</subfield>
            </datafield>"""
        )
        assert read_description(rec) == expect

    def test_multiple_520_fields_are_paragraphs(self):
        rec = marc_520(
            """
            <datafield tag="520" ind1=" " ind2=" ">
              <subfield code="a">"A gripping tale."--</subfield>
              <subfield code="c">Back cover.</subfield>
            </datafield>
            <datafield tag="520" ind1="1" ind2=" ">
              <subfield code="a">"Horn is at the top of his game."--</subfield>
              <subfield code="c">Booklist.</subfield>
            </datafield>"""
        )
        assert read_description(rec) == ('"A gripping tale."--Back cover.\n\nReview: "Horn is at the top of his game."--Booklist.')

    def test_empty_520_contributes_nothing(self):
        rec = marc_520(
            """
            <datafield tag="520" ind1="1" ind2=" ">
              <subfield code="a"></subfield>
            </datafield>
            <datafield tag="520" ind1=" " ind2=" ">
              <subfield code="a">Kept.</subfield>
            </datafield>"""
        )
        assert read_description(rec) == "Kept."
