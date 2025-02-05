from openlibrary.catalog.marc.mnemonics import read


def test_read_conversion_to_marc8():
    input_ = b'Tha{mllhring}{macr}alib{macr}i, {mllhring}Abd al-Malik ibn Mu{dotb}hammad,'  # codespell:ignore
    output = (
        b'Tha\xb0\xe5alib\xe5i, \xb0Abd al-Malik ibn Mu\xf2hammad,'  # codespell:ignore
    )
    assert read(input_) == output


def test_read_no_change():
    input_ = b'El Ing.{eniero} Federico E. Capurro y el nacimiento de la profesi\xe2on bibliotecaria en el Uruguay.'
    assert read(input_) == input_
