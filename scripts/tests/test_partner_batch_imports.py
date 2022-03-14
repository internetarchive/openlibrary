import pytest
from ..partner_batch_imports import Biblio

csv_row = "USA01961304|0962561851||9780962561856|AC|I|TC||B||Sutra on Upasaka Precepts|The||||||||2006|20060531|Heng-ching, Shih|TR||||||||||||||226|ENG||0.545|22.860|15.240|||||||P|||||||74474||||||27181|USD|30.00||||||||||||||||||||||||||||SUTRAS|BUDDHISM_SACRED BOOKS|||||||||REL007030|REL032000|||||||||HRES|HRG|||||||||RB,BIP,MIR,SYN|1961304|00|9780962561856|67499962||PRN|75422798|||||||BDK America||1||||||||10.1604/9780962561856|91-060120||20060531|||||REL007030||||||"  # noqa: E501


non_books = [
    "USA39372027|8866134201||9788866134206|AC|I|DI||||Moleskine Cahier Journal (Set of 3), Pocket, Ruled, Pebble Grey, Soft Cover (3. 5 X 5. 5)||||||||||20120808|Moleskine|AU|X|||||||||||||64|ENG||0.126|13.970|8.890|1.270|X|||||T|||Cahier Journals||||1161400||||||333510|USD|9.95||||||||||||||||||||||||||||||||||||||||||||||||||||||||||BIP,OTH|39372027|01|9788866134206|69270822|||29807389||||||2328606|Moleskine||1|||||||||||||||NO|NON000000|||WZS|||",  # noqa: E501
    "AUS52496256|1452145865||9781452145860|AC|I|ZZ||||People Pencils : 10 Graphite Pencils||||||||||20160501|Sukie|AU|X|||||||||||||10|ENG||0.170|19.685|8.890|2.235|X|||||T|||||||5882||||||1717043|AUD|24.99||||||||||||||||||||||||||||NON-CLASSIFIABLE||||||||||NON000000||||||||||||||||||||BIP,OTH|52496256|02|9781452145860|51743426|||48922851|||||||Chronicle Books LLC||80|||||||||||||||NO|ART048000|||AFH|WZS||",  # noqa: E501
    "AUS49413469|1423638298||9781423638292|AC|I|ZZ||O||Keep Calm and Hang on Mug|||1 vol.|||||||20141201|Gibbs Smith Publisher Staff|DE|X||||||||||||||ENG||0.350|7.620|9.322|9.449||||||T|||||||20748||||||326333|AUD|22.99||||||||||||||||||||||||||||||||||||||||||||||||||||||||||BIP,OTH|49413469||9781423638292|50573089||OTH|1192128|||||||Gibbs Smith, Publisher||7||||||||||||||||NON000000|||WZ|||",  # noqa: E501
]

class TestBiblio:
    def test_sample_csv_row(self):
        b = Biblio(csv_row.strip().split('|'))
        data = {
            'title': 'Sutra on Upasaka Precepts',
            'isbn_13': ['9780962561856'],
            'publish_date': '2006',
            'publishers': ['BDK America'],
            'weight': '0.545',
            'authors': [{'name': 'Heng-ching, Shih'}],
            'pagination': '226',
            'languages': ['eng'],
            'subjects': ['Sutras', 'Buddhism, sacred books'],
            'source_records': ['bwb:9780962561856'],
        }
        assert b.json() == data

    @pytest.mark.parametrize('input_', non_books)
    def test_non_books_rejected(self, input_):
        data = input_.strip().split('|')
        code = data[6]
        with pytest.raises(AssertionError, match=f'{code} is NONBOOK'):
            b = Biblio(data)
