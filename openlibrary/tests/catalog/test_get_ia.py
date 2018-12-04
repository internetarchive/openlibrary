from __future__ import print_function
import os
import pytest
from openlibrary.catalog import get_ia
from openlibrary.core import ia
from openlibrary.catalog.marc.marc_xml import MarcXml
from openlibrary.catalog.marc.marc_binary import MarcBinary, BadLength, BadMARC

def return_test_marc_bin(url):
    return return_test_marc_data(url, "bin_input")

def return_test_marc_xml(url):
    return return_test_marc_data(url, "xml_input")

def return_test_marc_data(url, test_data_subdir="xml_input"):
    filename = url.split("/")[-1]
    test_data_dir = "/../../catalog/marc/tests/test_data/%s/" % test_data_subdir
    path = os.path.dirname(__file__) + test_data_dir + filename
    return open(path)

class TestGetIA():
    bad_marcs = ['1733mmoiresdel00vill', # Binary MARC reports len=734, but actually=742. Has badly converted unicode
                                         # original unicode converted as if it were MARC8
                 'dasrmischepriv00rein', # same as zweibchersatir01horauoft, binary representation of unicode interpreted as unicode codepoints
                 'histoirereligieu05cr', # C3A2 in this file should be single byte MARC8 combining acute 0xE2
                                         # Original MARC8 0xE2 interpreted as u00E2 => \xC3\xA2, leader still MARC8
                 'lesabndioeinas00sche', # Original MARC8 0xE2 interpreted as u00E2 => \xC3\xA2, leader still MARC8
                 'poganucpeoplethe00stowuoft', # junk / unexpected character at end of publishers in field 260
                 'scrapbooksofmoun03tupp', # possible extra chars at end of field 505?
                 'zweibchersatir01horauoft', # leader is unicode, chars '\xc3\x83\xc2\xbc' in mrc should be '\xc3\xbc'
                                             # original '\xc3\xb3' was converted to '\u00c3\u00b3'
                ]

    bin_items = ['0descriptionofta1682unit',
                 '13dipolarcycload00burk',
                 'bijouorannualofl1828cole',
                 'cu31924091184469',
                 'diebrokeradical400poll',
                 'engineercorpsofh00sher',
                 'flatlandromanceo00abbouoft',
                 'henrywardbeecher00robauoft',
                 'lincolncentenary00horn',
                 'livrodostermosh00bragoog',
                 'mytwocountries1954asto',
                 'onquietcomedyint00brid',
                 'secretcodeofsucc00stjo',
                 'thewilliamsrecord_vol29b',
                 'warofrebellionco1473unit',
                ]

    xml_items = ['1733mmoiresdel00vill',     # no <?xml
                 '0descriptionofta1682unit', # has <?xml
                 'cu31924091184469',         # is <collection>
                 #'1893manualofharm00jadauoft', # 0 byte xml file
                 '00schlgoog',
                 '13dipolarcycload00burk',
                 '39002054008678.yale.edu',
                 'abhandlungender01ggoog',
                 'bijouorannualofl1828cole',
                 'dasrmischepriv00rein',
                 'diebrokeradical400poll',
                 'engineercorpsofh00sher',
                 'flatlandromanceo00abbouoft',
                 'lesabndioeinas00sche',
                 'lincolncentenary00horn',
                 'livrodostermosh00bragoog',
                 'mytwocountries1954asto',
                 'nybc200247',
                 'onquietcomedyint00brid',
                 'scrapbooksofmoun03tupp',
                 'secretcodeofsucc00stjo',
                 'soilsurveyrepor00statgoog',
                 'warofrebellionco1473unit',
                 'zweibchersatir01horauoft',
                ]

    @pytest.mark.parametrize('item', xml_items)
    def test_get_marc_record_from_ia(self, item, monkeypatch):
        """Tests the method returning MARC records from IA
        used by the import API. It should return an XML MARC if one exists."""
        monkeypatch.setattr(get_ia, 'urlopen_keep_trying', return_test_marc_xml)
        monkeypatch.setattr(ia, 'get_metadata', lambda itemid: {'_filenames': [itemid + '_marc.xml', itemid + '_meta.mrc']})

        result = get_ia.get_marc_record_from_ia(item)
        assert isinstance(result, MarcXml), \
            "%s: expected instanceof MarcXml, got %s" % (item, type(result))

    @pytest.mark.parametrize('item', bin_items)
    def test_no_marc_xml(self, item, monkeypatch):
        """When no XML MARC is listed in _filenames, the Binary MARC should be fetched."""
        monkeypatch.setattr(get_ia, 'urlopen_keep_trying', return_test_marc_bin)
        monkeypatch.setattr(ia, 'get_metadata', lambda itemid: {'_filenames': [itemid + "_meta.mrc"]})

        result = get_ia.get_marc_record_from_ia(item)
        assert isinstance(result, MarcBinary), \
            "%s: expected instanceof MarcBinary, got %s" % (item, type(result))
        print("%s:\n\tUNICODE: [%s]\n\tTITLE: %s" % (item,
                                                     result.leader()[9],
                                                     result.read_fields(['245']).next()[1].get_all_subfields().next()[1].encode('utf8')))

    @pytest.mark.parametrize('bad_marc', bad_marcs)
    def test_incorrect_length_marcs(self, bad_marc, monkeypatch):
        """If a Binary MARC has a different length than stated in the MARC leader, it is probably due to bad character conversions."""
        monkeypatch.setattr(get_ia, 'urlopen_keep_trying', return_test_marc_bin)
        monkeypatch.setattr(ia, 'get_metadata', lambda itemid: {'_filenames': [itemid + "_meta.mrc"]})

        with pytest.raises(BadLength):
            result = get_ia.get_marc_record_from_ia(bad_marc)

    def test_bad_binary_data(self):
        with pytest.raises(BadMARC):
            result = MarcBinary('nonMARCdata')
