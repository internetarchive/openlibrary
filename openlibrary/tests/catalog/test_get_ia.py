import os
import unittest
from _pytest.monkeypatch import monkeypatch
from openlibrary.catalog import get_ia
from openlibrary.core import ia
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
        xml_items = ["1733mmoiresdel00vill",     # no <?xml
                     "0descriptionofta1682unit"] # has <?xml
        m = monkeypatch()
        m.setattr(get_ia, 'urlopen_keep_trying', return_test_marc_data)
        m.setattr(ia, 'get_metadata', lambda itemid: {'_filenames': [itemid + "_marc.xml", itemid + "_meta.mrc"]})

        for item in xml_items:
            result = get_ia.get_marc_record_from_ia(item)
            self.assertIsInstance(result, MarcXml)

