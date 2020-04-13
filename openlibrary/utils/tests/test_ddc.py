import pytest

from openlibrary.utils.ddc import normalize_ddc

# Src: https://www.oclc.org/bibformats/en/0xx/082.html
TESTS_FROM_OCLC = [
    ("370.19'342", ['370.19342'], "Segmentation (prime) marks"),
    ("370.19/342", ['370.19342'], "Segmentation (prime) marks"),
    ("j574", ['j574'], "Juvenile works."),
    ("[E]", ['[E]'], "Juvenile works with [E]"),
    ("[Fic]", ['[Fic]'], "Juvenile works with [Fic]."),
    ("658.404 92", ['658.404 92'], "Dewey numbers followed by 92 or 920."),
    ("658.404 920", ['658.404 920'], "Dewey numbers followed by 92 or 920."),
    ("942.082 [B]", ['942.082 B'], "Uppercase B in post-1971 numbers."),
    ("*657.6", ['657.6*'],
     "LC assigned Dewey numbers according to both the 14th and the 15th editions of "
     "the Dewey schedules."),
    ("*735.29 735.42", ['735.29*', '735.42'],
     "LC assigned Dewey numbers according to both the 14th and the 15th editions of "
     "the Dewey schedules."),
    ("081s", ['081 s'], "Series numbers."),
    ("081 s", ['081 s'], "Series numbers."),
    ("(015.73)", ['015.73 s'],
     "Parentheses indicating Dewey numbers assigned to a series."),
    ("015.73 s", ['015.73 s'],
     "Parentheses indicating Dewey numbers assigned to a series."),
    ("(015.73) 015.791", ['015.73 s', '015.791'],
     "Two Dewey numbers: one in parentheses, one not."),
    ("-222.14", ['-222.14'], "Dewey numbers with minus signs."),
    ("-222.14 (927.5)", ['-222.14', '927.5 s'], "Dewey numbers with minus signs."),
    ("[320.9777]", ['320.9777'], "Dewey numbers in brackets."),
    ("[016.3584] 012", ['016.3584', '012'], "Dewey numbers in brackets."),
    ("081s [370.19'342]", ['081 s', '370.19342'],
     "Dewey number followed by lowercase s and a second number in brackets."),
    ("C364/.971", ['364.971'], "Canadian CIP"),
]
TESTS = [
    ('123', ['123'], 'whole number'),
    ('1', ['001'], 'whole number padding'),
    ('hello world!', [], 'junk'),
    ('978123412341', [], 'junk'),
]


@pytest.mark.parametrize("raw_ddc,expected,name", TESTS, ids=[t[2] for t in TESTS])
def test_noramlize_ddc(raw_ddc, expected, name):
    assert normalize_ddc(raw_ddc) == expected


@pytest.mark.parametrize("raw_ddc,expected,name", TESTS_FROM_OCLC,
                         ids=[t[2] for t in TESTS_FROM_OCLC])
def test_normalize_ddc_with_oclc_spec(raw_ddc, expected, name):
    assert normalize_ddc(raw_ddc) == expected
