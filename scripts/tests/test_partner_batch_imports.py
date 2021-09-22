from ..partner_batch_imports import Biblio

csv_row = "USA01961304|0962561851||9780962561856|AC|I|TC||B||Sutra on Upasaka Precepts|The||||||||2006|20060531|Heng-ching, Shih|TR||||||||||||||226|ENG||0.545|22.860|15.240|||||||P|||||||74474||||||27181|USD|30.00||||||||||||||||||||||||||||SUTRAS|BUDDHISM_SACRED BOOKS|||||||||REL007030|REL032000|||||||||HRES|HRG|||||||||RB,BIP,MIR,SYN|1961304|00|9780962561856|67499962||PRN|75422798|||||||BDK America||1||||||||10.1604/9780962561856|91-060120||20060531|||||REL007030||||||"  # noqa: E501


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
            'number_of_pages': '226',
            'languages': ['eng'],
            'subjects': ['Sutras', 'Buddhism, sacred books'],
            'source_records': ['bwb:9780962561856']
        }
        assert b.json() == data
