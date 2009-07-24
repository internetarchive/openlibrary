import py.test
from openlibrary.plugins.openlibrary.showmarc import show_marc, show_ia

@py.test.mark(online=True)
def test_showmarc():
    show_marc().GET('/marc_records_scriblio_net/part29.dat', 0, 519)

@py.test.mark(online=True)
def test_showia():
    show_ia().GET('atestimonyconce00meetgoog')

