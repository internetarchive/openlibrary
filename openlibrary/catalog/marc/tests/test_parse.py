import pytest

from openlibrary.catalog.marc.parse import (
    read_author_person, read_edition, NoTitle, SeeAlsoAsTitle)
from openlibrary.catalog.marc.marc_binary import MarcBinary
from openlibrary.catalog.marc.marc_xml import DataField, MarcXml
from lxml import etree
import os
import simplejson

collection_tag = '{http://www.loc.gov/MARC21/slim}collection'
record_tag = '{http://www.loc.gov/MARC21/slim}record'

xml_samples = ['39002054008678.yale.edu', 'flatlandromanceo00abbouoft',
    'nybc200247', 'secretcodeofsucc00stjo', 'warofrebellionco1473unit',
    'zweibchersatir01horauoft', 'onquietcomedyint00brid', '00schlgoog',
    '0descriptionofta1682unit', '1733mmoiresdel00vill', '13dipolarcycload00burk',
    'bijouorannualofl1828cole', 'soilsurveyrepor00statgoog', 'diebrokeradical400poll',
    'cu31924091184469', # MARC XML collection record
    'engineercorpsofh00sher',
    ]

bin_samples = [
    'bijouorannualofl1828cole_meta.mrc', 'onquietcomedyint00brid_meta.mrc',  # LCCN with leading characters
    'merchantsfromcat00ben_meta.mrc', 'memoirsofjosephf00fouc_meta.mrc',  # MARC8 encoded with e-acute
    'equalsign_title.mrc',  # Title ending in '='
    'bpl_0486266893', 'flatlandromanceo00abbouoft_meta.mrc',
    'histoirereligieu05cr_meta.mrc', 'ithaca_college_75002321', 'lc_0444897283',
    'lc_1416500308', 'ocm00400866', 'secretcodeofsucc00stjo_meta.mrc',
    'uoft_4351105_1626', 'warofrebellionco1473unit_meta.mrc', 'wrapped_lines',
    'wwu_51323556', 'zweibchersatir01horauoft_meta.mrc', 'talis_two_authors.mrc',
    'talis_no_title.mrc', 'talis_740.mrc', 'talis_245p.mrc', 'talis_856.mrc',
    'talis_multi_work_tiles.mrc', 'talis_empty_245.mrc', 'ithaca_two_856u.mrc',
    'collingswood_bad_008.mrc', 'collingswood_520aa.mrc', 'upei_broken_008.mrc',
    'upei_short_008.mrc', 'diebrokeradical400poll_meta.mrc', 'cu31924091184469_meta.mrc',
    'engineercorpsofh00sher_meta.mrc', 'henrywardbeecher00robauoft_meta.mrc',
    'thewilliamsrecord_vol29b_meta.mrc', '13dipolarcycload00burk_meta.mrc' ]

test_data = "%s/test_data" % os.path.dirname(__file__)

class TestParseMARCXML:
    @pytest.mark.parametrize('i', xml_samples)
    def test_xml(self, i):
        expect_filename = "%s/xml_expect/%s_marc.xml" % (test_data, i)
        path            = "%s/xml_input/%s_marc.xml"  % (test_data, i)
        element = etree.parse(open(path)).getroot()
        # Handle MARC XML collection elements in our test_data expectations:
        if element.tag == collection_tag and element[0].tag == record_tag:
            element = element[0]
        rec = MarcXml(element)
        edition_marc_xml = read_edition(rec)
        assert edition_marc_xml
        j = simplejson.load(open(expect_filename))
        assert j, 'Unable to open test data: %s' % expect_filename
        assert sorted(edition_marc_xml.keys()) == sorted(j.keys()), 'Processed MARCXML fields do not match expectations in %s' % expect_filename
        for k in edition_marc_xml.keys():
            assert edition_marc_xml[k] == j[k], 'Processed MARCXML values do not match expectations in %s' % expect_filename
        assert edition_marc_xml == j


class TestParseMARCBinary:
    @pytest.mark.parametrize('i', bin_samples)
    def test_binary(self, i):
        expect_filename = "%s/bin_expect/%s" % (test_data, i)
        data = open("%s/bin_input/%s" % (test_data, i)).read()
        if len(data) != int(data[:5]):
            #TODO: Why are we fixing this in test expectations? Investigate.
            #      affects histoirereligieu05cr_meta.mrc and zweibchersatir01horauoft_meta.mrc
            data = data.decode('utf-8').encode('raw_unicode_escape')
        assert len(data) == int(data[:5])
        rec = MarcBinary(data)
        edition_marc_bin = read_edition(rec)
        assert edition_marc_bin
        if not os.path.exists(expect_filename):
            # Missing test expectations file. Create a template from the input, but fail the current test.
            simplejson.dump(edition_marc_bin, open(expect_filename, 'w'), indent=2)
            assert False, 'Expectations file %s not found: template generated in %s. Please review and commit this file.' % (expect_filename, '/bin_expect')
        j = simplejson.load(open(expect_filename))
        assert j, 'Unable to open test data: %s' % expect_filename
        assert sorted(edition_marc_bin.keys()) == sorted(j.keys()), 'Processed binary MARC fields do not match expectations in %s' % expect_filename
        for k in edition_marc_bin.keys():
            if isinstance(j[k], list):
                for item1, item2 in zip(edition_marc_bin[k], j[k]):
                    assert item1 == item2
            assert edition_marc_bin[k] == j[k], 'Processed binary MARC values do not match expectations in %s' % expect_filename
        assert edition_marc_bin == j

    def test_raises_see_also(self):
        filename = '%s/bin_input/talis_see_also.mrc' % test_data
        with open(filename, 'r') as f:
            rec = MarcBinary(f.read())
        with pytest.raises(SeeAlsoAsTitle):
            read_edition(rec)

    def test_raises_no_title(self):
        filename = '%s/bin_input/talis_no_title2.mrc' % test_data
        with open(filename, 'r') as f:
            rec = MarcBinary(f.read())
        with pytest.raises(NoTitle):
            read_edition(rec)


class TestParse:
    def test_read_author_person(self):
        xml_author = """
        <datafield xmlns="http://www.loc.gov/MARC21/slim" tag="100" ind1="1" ind2="0">
          <subfield code="a">Rein, Wilhelm,</subfield>
          <subfield code="d">1809-1865</subfield>
        </datafield>"""
        test_field = DataField(etree.fromstring(xml_author))
        result = read_author_person(test_field)

        # Name order remains unchanged from MARC order
        assert result['name'] == result['personal_name'] == 'Rein, Wilhelm'
        assert result['birth_date'] == '1809'
        assert result['death_date'] == '1865'
        assert result['entity_type'] == 'person'
