#!/usr/bin/python
import unittest

from parse import read_edition, SeeAlsoAsTitle, NoTitle
from marc_binary import MarcBinary
from marc_xml import MarcXml, BadSubtag, BlankTag
from urllib import urlopen
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

bin_samples = ['bpl_0486266893', 'flatlandromanceo00abbouoft_meta.mrc',
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

class TestParse(unittest.TestCase):
    def test_xml(self):
        for i in xml_samples:
            try:
                expect_filename = "%s/xml_expect/%s_marc.xml" % (test_data, i)
                path            = "%s/xml_input/%s_marc.xml"  % (test_data, i)
                element = etree.parse(open(path)).getroot()
                # Handle MARC XML collection elements in our test_data expectations:
                if element.tag == collection_tag and element[0].tag == record_tag:
                    element = element[0]
                rec = MarcXml(element)
                edition_marc_xml = read_edition(rec)
                assert edition_marc_xml
                j = {}
                if os.path.exists(expect_filename):
                    j = simplejson.load(open(expect_filename))
                    assert j, "Unable to open test data: %s" % expect_filename
                else:
                    print "WARNING: test data %s not found, recreating it!" % expect_filename
                    simplejson.dump(edition_marc_xml, open(expect_filename, 'w'), indent=2)
                    continue
                self.assertEqual(sorted(edition_marc_xml.keys()), sorted(j.keys()))
                for k in edition_marc_xml.keys():
                    self.assertEqual(edition_marc_xml[k], j[k])
                self.assertEqual(edition_marc_xml, j)
            except:
                print 'Bad MARC:', i
                raise

    def test_binary(self):
        for i in bin_samples:
            try:
                expect_filename = "%s/bin_expect/%s" % (test_data, i)
                data = open("%s/bin_input/%s" % (test_data, i)).read()
                if len(data) != int(data[:5]):
                    data = data.decode('utf-8').encode('raw_unicode_escape')
                assert len(data) == int(data[:5])
                rec = MarcBinary(data)
                edition_marc_bin = read_edition(rec)
                assert edition_marc_bin
                j = {}
                if os.path.exists(expect_filename):
                    j = simplejson.load(open(expect_filename))
                    assert j, "Unable to open test data: %s" % expect_filename
                else:
                    print "WARNING: test data %s not found, recreating it!" % expect_filename
                    simplejson.dump(edition_marc_bin, open(expect_filename, 'w'), indent=2)
                    continue
                self.assertEqual(sorted(edition_marc_bin.keys()), sorted(j.keys()))
                for k in edition_marc_bin.keys():
                    if isinstance(j[k], list):
                        for item1, item2 in zip(edition_marc_bin[k], j[k]):
                            self.assertEqual(item1, item2)

                    self.assertEqual(edition_marc_bin[k], j[k])
                self.assertEqual(edition_marc_bin, j)
            except:
                print 'Bad MARC:', i
                raise

    def test_raises_see_also(self):
        filename = "%s/bin_input/talis_see_also.mrc" % test_data
        with open(filename, 'r') as f:
            rec = MarcBinary(f.read())
        self.assertRaises(SeeAlsoAsTitle, read_edition, rec)

    def test_raises_no_title(self):
        filename = "%s/bin_input/talis_no_title2.mrc" % test_data
        with open(filename, 'r') as f:
            rec = MarcBinary(f.read())
        self.assertRaises(NoTitle, read_edition, rec)

