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

    @pytest.mark.parametrize('item', bin_items)
    def test_get_marc_record_from_ia(self, item, monkeypatch):
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
        result = get_ia.get_marc_record_from_ia(item)
        assert isinstance(
            result, MarcBinary
        ), f"{item}: expected instanceof MarcBinary, got {type(result)}"

    @pytest.mark.parametrize('item', xml_items)
    def test_no_marc_xml(self, item, monkeypatch):
        """When no binary MARC is listed in _filenames, the MARC XML should be fetched."""
        monkeypatch.setattr(get_ia, 'urlopen_keep_trying', return_test_marc_xml)
        monkeypatch.setattr(
            ia, 'get_metadata', lambda itemid: {'_filenames': [f'{itemid}_marc.xml']}
        )
        result = get_ia.get_marc_record_from_ia(item)
        assert isinstance(
            result, MarcXml
        ), f"{item}: expected instanceof MarcXml, got {type(result)}"

    @pytest.mark.parametrize('bad_marc', bad_marcs)
    def test_incorrect_length_marcs(self, bad_marc, monkeypatch):
        """If a Binary MARC has a different length than stated in the MARC leader, it is probably due to bad character conversions."""
        monkeypatch.setattr(get_ia, 'urlopen_keep_trying', return_test_marc_bin)
        monkeypatch.setattr(
            ia, 'get_metadata', lambda itemid: {'_filenames': [f'{itemid}_meta.mrc']}
        )
        with pytest.raises(BadLength):
            result = get_ia.get_marc_record_from_ia(bad_marc)

    def test_bad_binary_data(self):
        with pytest.raises(BadMARC):
            result = MarcBinary('nonMARCdata')
