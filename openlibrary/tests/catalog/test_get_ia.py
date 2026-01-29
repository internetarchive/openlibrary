from pathlib import Path

import pytest

from openlibrary.catalog import get_ia
from openlibrary.catalog.marc.marc_binary import BadLength, BadMARC, MarcBinary
from openlibrary.catalog.marc.marc_xml import MarcXml
from openlibrary.core import ia

TEST_DATA = Path(__file__).parents[2] / 'catalog' / 'marc' / 'tests' / 'test_data'


class MockResponse:
    """MockResponse is used to pass the contents of the read file back as an object that acts like a requests.Response
    object instead of a file object.  This is because the urlopen_keep_trying function was moved from urllib to requests.
    """

    def __init__(self, data):
        self.content = data
        self.text = data.decode('utf-8')


def return_test_marc_bin(url):
    return return_test_marc_data(url, 'bin_input')


def return_test_marc_xml(url):
    return return_test_marc_data(url, 'xml_input')


def return_test_marc_data(url, test_data_subdir='xml_input'):
    filename = url.split('/')[-1]
    path = TEST_DATA / test_data_subdir / filename
    return MockResponse(path.read_bytes())


class TestGetIA:
    bad_marcs: tuple[str, ...] = (
        'dasrmischepriv00rein',  # binary representation of unicode interpreted as unicode codepoints
        'lesabndioeinas00sche',  # Original MARC8 0xE2 interpreted as u00E2 => \xC3\xA2, leader still MARC8
        'poganucpeoplethe00stowuoft',  # junk / unexpected character at end of publishers in field 260
    )

    bin_items: tuple[str, ...] = (
        '0descriptionofta1682unit',
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
    )

    xml_items: tuple[str, ...] = (
        '1733mmoiresdel00vill',  # no <?xml
        '0descriptionofta1682unit',  # has <?xml
        'cu31924091184469',  # is <collection>
        '00schlgoog',
        '13dipolarcycload00burk',
        '39002054008678_yale_edu',
        'abhandlungender01ggoog',
        'bijouorannualofl1828cole',
        'dasrmischepriv00rein',
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
    )

    def test_get_marc_record_from_ia(self, subtests, monkeypatch):
        """Tests the method returning MARC records from IA
        used by the import API. It should return a binary MARC if one exists."""
        monkeypatch.setattr(get_ia, 'urlopen_keep_trying', return_test_marc_bin)
        monkeypatch.setattr(
            ia,
            'get_metadata',
            lambda itemid: {
                '_filenames': [f'{itemid}_{s}' for s in ('marc.xml', 'meta.mrc')]
            },
        )

        for item in self.bin_items:
            with subtests.test(msg=item):
                result = get_ia.get_marc_record_from_ia(item)
                assert isinstance(
                    result, MarcBinary
                ), f"{item}: expected instanceof MarcBinary, got {type(result)}"

    def test_no_marc_xml(self, subtests, monkeypatch):
        """When no binary MARC is listed in _filenames, the MARC XML should be fetched.

        This uses pytest 9.0's subtests feature to test all XML MARC items in a single test.
        Benefits over parametrize:
        - Reports ALL errors in one run (doesn't stop at first failure)
        - Cleaner test output (not dozens of separate test cases)
        - Easier to identify which items have issues
        """
        monkeypatch.setattr(get_ia, 'urlopen_keep_trying', return_test_marc_xml)
        monkeypatch.setattr(
            ia, 'get_metadata', lambda itemid: {'_filenames': [f'{itemid}_marc.xml']}
        )

        for item in self.xml_items:
            with subtests.test(msg=item):
                result = get_ia.get_marc_record_from_ia(item)
                assert isinstance(
                    result, MarcXml
                ), f"{item}: expected instanceof MarcXml, got {type(result)}"

    def test_incorrect_length_marcs(self, subtests, monkeypatch):
        monkeypatch.setattr(get_ia, 'urlopen_keep_trying', return_test_marc_bin)
        monkeypatch.setattr(
            ia, 'get_metadata', lambda itemid: {'_filenames': [f'{itemid}_meta.mrc']}
        )

        for bad_marc in self.bad_marcs:
            with subtests.test(msg=bad_marc), pytest.raises(BadLength):
                get_ia.get_marc_record_from_ia(bad_marc)

    def test_bad_binary_data(self):
        with pytest.raises(BadMARC):
            MarcBinary('nonMARCdata')

    @pytest.mark.xfail(
        reason="Verification test: demonstrates MARC type error detection"
    )
    def test_marc_type_error_detection_verification(self, monkeypatch):
        """Verify that MARC type error detection works.

        This is a simple verification test to prove that error detection works.
        """
        monkeypatch.setattr(get_ia, 'urlopen_keep_trying', return_test_marc_bin)
        monkeypatch.setattr(
            ia,
            'get_metadata',
            lambda itemid: {'_filenames': [f'{itemid}_meta.mrc']},
        )

        result = get_ia.get_marc_record_from_ia('0descriptionofta1682unit')

        # This WILL fail - wrong type check
        assert isinstance(result, str), f"Result should be string not {type(result)}"
