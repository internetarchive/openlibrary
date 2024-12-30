from pathlib import Path

from openlibrary.catalog.marc.marc_binary import BinaryDataField, MarcBinary

TEST_DATA = Path(__file__).with_name('test_data') / 'bin_input'


class MockMARC:
    def __init__(self, encoding):
        """
        :param encoding str: 'utf8' or 'marc8'
        """
        self.encoding = encoding

    def marc8(self):
        return self.encoding == 'marc8'


def test_wrapped_lines():
    filepath = TEST_DATA / 'wrapped_lines.mrc'
    rec = MarcBinary(filepath.read_bytes())
    ret = list(rec.read_fields(['520']))
    assert len(ret) == 2
    a, b = ret
    assert a[0] == '520'
    assert b[0] == '520'
    a_content = next(iter(a[1].get_all_subfields()))[1]
    assert len(a_content) == 2290
    b_content = next(iter(b[1].get_all_subfields()))[1]
    assert len(b_content) == 243


class Test_BinaryDataField:
    def test_translate(self):
        bdf = BinaryDataField(MockMARC('marc8'), b'')
        assert (
            bdf.translate(b'Vieira, Claudio Bara\xe2una,') == 'Vieira, Claudio Baraúna,'
        )

    def test_bad_marc_line(self):
        line = (
            b'0 \x1f\xe2aEtude objective des ph\xe2enom\xe1enes neuro-psychiques;\x1e'
        )
        bdf = BinaryDataField(MockMARC('marc8'), line)
        assert list(bdf.get_all_subfields()) == [
            ('á', 'Etude objective des phénomènes neuro-psychiques;')
        ]


class Test_MarcBinary:
    def test_read_fields_returns_all(self):
        filepath = TEST_DATA / 'onquietcomedyint00brid_meta.mrc'
        rec = MarcBinary(filepath.read_bytes())
        fields = list(rec.read_fields())
        assert len(fields) == 13
        assert fields[0][0] == '001'
        for f, v in fields:
            if f == '001':
                f001 = v
            elif f == '008':
                f008 = v
            elif f == '100':
                f100 = v
        assert isinstance(f001, str)
        assert isinstance(f008, str)
        assert isinstance(f100, BinaryDataField)

    def test_get_subfield_value(self):
        filepath = TEST_DATA / 'onquietcomedyint00brid_meta.mrc'
        rec = MarcBinary(filepath.read_bytes())
        author_field = rec.get_fields('100')
        assert isinstance(author_field, list)
        assert isinstance(author_field[0], BinaryDataField)
        subfields = author_field[0].get_subfields('a')
        assert next(subfields) == ('a', 'Bridgham, Gladys Ruth. [from old catalog]')
        values = author_field[0].get_subfield_values('a')
        (name,) = values  # 100$a is non-repeatable, there will be only one
        assert name == 'Bridgham, Gladys Ruth. [from old catalog]'
