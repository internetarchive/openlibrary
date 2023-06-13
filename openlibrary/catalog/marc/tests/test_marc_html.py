import os
from openlibrary.catalog.marc.html import html_record


TEST_DATA = f'{os.path.dirname(__file__)}/test_data/bin_input/'


def test_html_line_marc8():
    expected_utf8 = (
        '<b>700</b> <code>1  <b>$a</b>Ovsi︠a︡nnikov, Mikhail Fedotovich.</code><br>'
    )
    with open(f'{TEST_DATA}uoft_4351105_1626.mrc', 'rb') as f:
        record = html_record(f.read())
    result = record.html()
    assert expected_utf8 in result
