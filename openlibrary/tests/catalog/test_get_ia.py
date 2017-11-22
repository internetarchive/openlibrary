import os
import unittest
from _pytest.monkeypatch import monkeypatch
from openlibrary.catalog import get_ia
from openlibrary.catalog.marc.marc_xml import MarcXml
from openlibrary.catalog.marc.marc_binary import MarcBinary

def return_test_marc_data(url):
    filename = url.split("/")[-1] 
    test_data_dir = "/../../catalog/marc/test_data/xml_input/"
    path = os.path.dirname(__file__) + test_data_dir + filename
    return open(path)

class TestGetIA(unittest.TestCase):
    def test_get_marc_record_from_ia(self):
        """Tests the method returning MARC records form IA
        used by the import API. It should return an XML MARC if one exists."""
        item = "1733mmoiresdel00vill"
        m = monkeypatch()
        m.setattr(get_ia, 'urlopen_keep_trying', return_test_marc_data)

        result = get_ia.get_marc_record_from_ia(item)
        self.assertIsInstance(result, MarcXml)

