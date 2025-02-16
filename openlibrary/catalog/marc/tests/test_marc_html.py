from pathlib import Path

from openlibrary.catalog.marc.html import html_record

TEST_DATA = Path(__file__).with_name('test_data') / 'bin_input'


def test_html_line_marc8():
    filepath = TEST_DATA / 'uoft_4351105_1626.mrc'
    expected_utf8 = (
        '<b>700</b> <code>1  <b>$a</b>Ovsi︠a︡nnikov, Mikhail Fedotovich.</code><br>'
    )
    record = html_record(filepath.read_bytes())
    result = record.html()
    assert expected_utf8 in result
