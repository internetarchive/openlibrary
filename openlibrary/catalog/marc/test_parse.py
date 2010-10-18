#!/usr/bin/python
import unittest

from parse import read_edition, SeeAlsoAsTitle, NoTitle
from marc_binary import MarcBinary
from marc_xml import MarcXml, BadSubtag, BlankTag
from pprint import pprint, pformat
from urllib import urlopen
from lxml import etree
import simplejson

record_tag = '{http://www.loc.gov/MARC21/slim}record'

xml_samples = ['39002054008678.yale.edu', 'flatlandromanceo00abbouoft',
    'nybc200247', 'secretcodeofsucc00stjo', 'warofrebellionco1473unit',
    'zweibchersatir01horauoft', 'onquietcomedyint00brid', '00schlgoog',
    '0descriptionofta1682unit', '1733mmoiresdel00vill', '13dipolarcycload00burk',
    'bijouorannualofl1828cole', 'soilsurveyrepor00statgoog', 'diebrokeradical400poll']

bin_samples = ['bpl_0486266893', 'flatlandromanceo00abbouoft_meta.mrc',
    'histoirereligieu05cr_meta.mrc', 'ithaca_college_75002321', 'lc_0444897283',
    'lc_1416500308', 'ocm00400866', 'secretcodeofsucc00stjo_meta.mrc',
    'uoft_4351105_1626', 'warofrebellionco1473unit_meta.mrc', 'wrapped_lines',
    'wwu_51323556', 'zweibchersatir01horauoft_meta.mrc', 'talis_two_authors.mrc',
    'talis_no_title.mrc', 'talis_740.mrc', 'talis_245p.mrc', 'talis_856.mrc',
    'talis_multi_work_tiles.mrc', 'talis_empty_245.mrc', 'ithaca_two_856u.mrc',
    'collingswood_bad_008.mrc', 'collingswood_520aa.mrc', 'upei_broken_008.mrc',
    'upei_short_008.mrc', 'diebrokeradical400poll_meta.mrc']

class TestParse(unittest.TestCase):
    def test_xml(self):
        for i in xml_samples:
            j = simplejson.load(open('test_data/xml_expect/' + i + '_marc.xml'))
            path = 'test_data/xml_input/' + i + '_marc.xml'
            element = etree.parse(open(path)).getroot()
            if element.tag != record_tag and element[0].tag == record_tag:
                element = element[0]
            rec = MarcXml(element)
            edition_marc_xml = read_edition(rec)
            self.assertEqual(sorted(edition_marc_xml.keys()), sorted(j.keys()))
            for k in edition_marc_xml.keys():
                self.assertEqual(edition_marc_xml[k], j[k])
            self.assertEqual(edition_marc_xml, j)

    def test_binary(self):
        for i in bin_samples:
            j = simplejson.load(open('test_data/bin_expect/' + i))
            data = open('test_data/bin_input/' + i).read()
            if len(data) != int(data[:5]):
                data = data.decode('utf-8').encode('raw_unicode_escape')
            assert len(data) == int(data[:5])
            rec = MarcBinary(data)
            edition_marc_bin = read_edition(rec)
            self.assertEqual(sorted(edition_marc_bin.keys()), sorted(j.keys()))
            for k in edition_marc_bin.keys():
                if isinstance(j[k], list):
                    for item1, item2 in zip(edition_marc_bin[k], j[k]):
                        self.assertEqual(item1, item2)

                self.assertEqual(edition_marc_bin[k], j[k])
            self.assertEqual(edition_marc_bin, j)

        i = 'talis_see_also.mrc'
        f = open('test_data/bin_input/' + i)
        rec = MarcBinary(f.read())
        self.assertRaises(SeeAlsoAsTitle, read_edition, rec)

        i = 'talis_no_title2.mrc'
        f = open('test_data/bin_input/' + i)
        rec = MarcBinary(f.read())
        self.assertRaises(NoTitle, read_edition, rec)
