import pytest

from openlibrary.utils.ddc import (
    choose_sorting_ddc,
    normalize_ddc,
    normalize_ddc_prefix,
    normalize_ddc_range,
)

# Src: https://www.oclc.org/bibformats/en/0xx/082.html
TESTS_FROM_OCLC = [
    ("370.19'342", ['370.19342'], "Segmentation (prime) marks"),
    ("370.19/342", ['370.19342'], "Segmentation (prime) marks"),
    ("j574", ['j574', '574'], "Juvenile works."),
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
    ("[016.3584] 012", ['016.3584'], "Dewey numbers in brackets."),
    ("081s [370.19'342]", ['081 s', '370.19342'],
     "Dewey number followed by lowercase s and a second number in brackets."),
    ("C364/.971", ['364.971'], "Canadian CIP"),
]
TESTS = [
    ('123', ['123'], 'whole number'),
    ('1', ['001'], 'whole number padding'),
    ('hello world!', [], 'junk'),
    ('978123412341', [], 'junk'),
    ('338.9/009171/7 019', ['338.90091717'],
     'Dewey number with segmentation and edition number'),
    ('332.6 021', ['332.6'], 'Dewey number and DDC edition number'),
    ('[E] 021', ['[E]'], 'Juvenile work and DDC edition number'),
    ('015', ['015'], 'Single Dewey number with edition number pattern'),
    ('(015.73) 015.791 021', ['015.73 s', '015.791'],
     'Two Dewey numbers and one edition number'),
    ('813. 54', ['813.54'], 'Space after decimal'),
    ('813.′54', ['813.54'], 'Curly quote separator (real world)'),
    ('813’.54', ['813.54'], 'Other kind of curly quote (real world)'),
    ('813. 54 (ddc21)', ['813.54'], 'catalog number with ddc prefix (real world)'),
    ('823/.92 22', ['823.92'], 'catalog number without leading 0 (real world)'),
    ("813.' 54", ['813.54'], 'Space and quote separate (real world)'),
    ("726. 6' 0945' 51 (ddc21)", ['726.6'], 'Random spaces (real world)'),
    ('813./​54', ['813.54'], 'Random non-printable chars (real world)'),
    ('868 G216m', ['868'], 'Cutter number (real world)'),
    ('863.,64', ['863.64'], 'Random comma (real world)'),
    ('616..8/3', ['616.83'], 'Double dot (real world)'),
    ('813.54 P38 1995', ['813.54'], 'Cutter/year (real world)'),
    ('21ddc', [], 'DDCs must end at word boundaries'),
    ('123; 216;', ['123', '216'], 'DDCs ending at word boundaries are ok'),
    ('[Fic] 2 21', ['[Fic]'], 'Ignores single digits after Fic'),
    ('[Fic] 813', ['[Fic]', '813'], 'Does not ignore tridigits after Fic'),
    ('813/.52/.52', ['813.52'], 'Too much decimal'),
]


@pytest.mark.parametrize("raw_ddc,expected,name", TESTS, ids=[t[2] for t in TESTS])
def test_noramlize_ddc(raw_ddc, expected, name):
    assert normalize_ddc(raw_ddc) == expected


@pytest.mark.parametrize("raw_ddc,expected,name", TESTS_FROM_OCLC,
                         ids=[t[2] for t in TESTS_FROM_OCLC])
def test_normalize_ddc_with_oclc_spec(raw_ddc, expected, name):
    assert normalize_ddc(raw_ddc) == expected


PREFIX_TESTS = [
    ('0', '0', 'Single number'),
    ('j', 'j', 'Only juvenile'),
    ('12', '12', 'Integer'),
    ('12.3', '012.3', 'Decimal'),
    ('12.300', '012.300', 'Trailing decimal zeros'),
    ('100', '100', 'Trailing zeros'),
    ('noise', 'noise', 'Noise'),
    ('j100', 'j100', 'Limited juvenile'),
]


@pytest.mark.parametrize("prefix,normed,name", PREFIX_TESTS,
                         ids=[t[-1] for t in PREFIX_TESTS])
def test_normalize_ddc_prefix(prefix, normed, name):
    assert normalize_ddc_prefix(prefix) == normed


RANGE_TESTS = [
    (['0', '3'], ['000', '003'], 'Single numbers'),
    (['100', '300'], ['100', '300'], 'Single numbers'),
    (['100', '*'], ['100', '*'], 'Star'),
]


@pytest.mark.parametrize("raw,normed,name", RANGE_TESTS,
                         ids=[t[-1] for t in RANGE_TESTS])
def test_normalize_ddc_range(raw, normed, name):
    assert normalize_ddc_range(*raw) == normed


SORTING_DDC_TEST = [
    (['123', '123.554'], '123.554', 'Chooses longest'),
    (['j123', '123'], '123', 'Prefer without j'),
    (['-222.14', '927.5'], '927.5', 'Prefer without -'),
    (['-222.14'], '-222.14', 'Begrudgingly uses prefixed if only option')
]


@pytest.mark.parametrize("ddcs,outpt,name", SORTING_DDC_TEST,
                         ids=[t[-1] for t in SORTING_DDC_TEST])
def test_choose_sorting_ddc(ddcs, outpt, name):
    assert choose_sorting_ddc(ddcs) == outpt
