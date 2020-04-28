import pytest

from openlibrary.utils.lcc import (
    normalize_lcc_prefix,
    normalize_lcc_range,
    short_lcc_to_sortable_lcc,
    sortable_lcc_to_short_lcc,
)

TESTS = [
    ('PZ-0073.00000000', 'pz73', 'PZ73', 'lower case'),
    ('PZ-0000.00000000', 'PZ', 'PZ', 'just class'),
    ('PZ-0123.00000000 [P]', 'PZ123 [P]', 'PZ123 [P]', 'keeps brackets at end'),
    ('BP-0166.94000000.S277 1999', '\\BP\\166.94\\.S277\\1999', 'BP166.94.S277 1999',
     'backslashes instead of spaces'),
    ('LC-6252.00000000.T4 T4 vol. 33, no. 10', '[LC6252.T4 T4 vol. 33, no. 10]',
     'LC6252.T4 T4 vol. 33, no. 10', 'brackets')
]


@pytest.mark.parametrize("sortable_lcc,raw_lcc,short_lcc,name", TESTS,
                         ids=[t[-1] for t in TESTS])
def test_to_sortable(sortable_lcc, raw_lcc, short_lcc, name):
    assert short_lcc_to_sortable_lcc(raw_lcc) == sortable_lcc


@pytest.mark.parametrize("sortable_lcc,raw_lcc,short_lcc,name", TESTS,
                         ids=[t[-1] for t in TESTS])
def test_to_short_lcc(sortable_lcc, raw_lcc, short_lcc, name):
    assert sortable_lcc_to_short_lcc(sortable_lcc) == short_lcc


INVALID_TESTS = [
    ('6113 .136', 'dewey decimal'),
    ('9608 BOOK NOT YET IN LC', 'noise'),
    ('#M8184', 'hash prefixed'),
    ('', 'empty'),
    ('MLCS 92/14990', 'too much class'),
    ('PZ123.234.234', 'too much decimal'),
    # The following are "real world" data from open library
    ('IN PROCESS', 'noise'),
    ('African Section Pamphlet Coll', 'real ol data'),
    ('Microfilm 99/20', 'real ol data'),
    ('Microfilm 61948 E', 'real ol data'),
    ('Microfiche 92/80965 (G)', 'real ol data'),
    ('MLCSN+', 'real ol data'),
    ('UNCLASSIFIED 809 (S)', 'real ol data'),
]


@pytest.mark.parametrize("text,name", INVALID_TESTS, ids=[t[-1] for t in INVALID_TESTS])
def test_invalid_lccs(text, name):
    assert short_lcc_to_sortable_lcc(text) is None


# Note: we don't handle all of these _entirely_ correctly as the paper says they should
# be, but we handle enough (See lcc.py)
# Src: https://ejournals.bc.edu/index.php/ital/article/download/11585/9839/
WAGNER_2019_EXAMPLES = [
    ('B--1190.00000000 1951', 'B1190 1951', 'no Cutter string'),
    ('DT-0423.00000000.E26 9th.ed. 2012', 'DT423.E26 9th.ed. 2012', 'compound spec'),
    ('E--0505.50000000 102nd.F57 1999', 'E505.5 102nd.F57 1999', 'ordinal in classif.'),
    ('HB-3717.00000000 1929.E37 2015', 'HB3717 1929.E37 2015 ', 'date in classif.'),
    ('KBD0000.00000000.G189s', 'KBD.G189s ', 'no caption number, no specification'),
    ('N--8354.00000000.B67 2000x', 'N8354.B67 2000x', 'date with suffix '),
    ('PS-0634.00000000.B4 1958-63', 'PS634.B4 1958-63', 'hyphenated range of dates'),
    ('PS-3557.00000000.A28R4 1955', 'PS3557.A28R4 1955', '"double Cutter"'),
    ('PZ-0008.30000000.G276Lo 1971', 'PZ8.3.G276Lo 1971 ', 'Cutter with "work mark"'),
    ('PZ-0073.00000000.S758345255 2011', 'PZ73.S758345255 2011', 'long Cutter decimal'),
]


@pytest.mark.parametrize("sortable_lcc,short_lcc,name", WAGNER_2019_EXAMPLES,
                         ids=[t[-1] for t in WAGNER_2019_EXAMPLES])
def test_wagner_2019_to_sortable(sortable_lcc, short_lcc, name):
    assert short_lcc_to_sortable_lcc(short_lcc) == sortable_lcc


@pytest.mark.parametrize("sortable_lcc,short_lcc,name", WAGNER_2019_EXAMPLES,
                         ids=[t[-1] for t in WAGNER_2019_EXAMPLES])
def test_wagner_2019_to_short_lcc(sortable_lcc, short_lcc, name):
    assert sortable_lcc_to_short_lcc(sortable_lcc) == short_lcc.strip()


PREFIX_TESTS = [
    ('A', 'A', 'Single letter'),
    ('ADC', 'ADC', 'multi letter'),
    ('A5', 'A--0005', 'Alphanum'),
    ('A5.00', 'A--0005.00', 'Alphanum'),
    ('A10', 'A--0010', 'Alphanum trailing 0'),
    ('A10.5', 'A--0010.5', 'Alphanum with decimal'),
    ('A10.', 'A--0010', 'Alphanum with trailing decimal'),
    ('A10.C', 'A--0010.00000000.C', 'Alphanum with partial cutter'),
    ('F349.N2 A77', 'F--0349.00000000.N2 A77', '2 cutters'),
    ('123', None, 'Invalid returns None'),
    ('*B55', None, 'Invalid returns None'),
]


@pytest.mark.parametrize("prefix,normed,name", PREFIX_TESTS,
                         ids=[t[-1] for t in PREFIX_TESTS])
def test_normalize_lcc_prefix(prefix, normed, name):
    assert normalize_lcc_prefix(prefix) == normed


RANGE_TESTS = [
    (['A', 'B'], ['A--0000.00000000', 'B--0000.00000000'], 'Single letters'),
    (['A1', 'A100'], ['A--0001.00000000', 'A--0100.00000000'], 'Letter nums'),
    (['A1', 'B1.13.C89'], ['A--0001.00000000', 'B--0001.13000000.C89'], 'Cutter num'),
    (['A1', 'noise'], ['A--0001.00000000', None], 'One Invalid'),
    (['blah', 'blah'], [None, None], 'Both invalid'),
    (['A1', '*'], ['A--0001.00000000', '*'], 'Star'),
]


@pytest.mark.parametrize("raw,normed,name", RANGE_TESTS,
                         ids=[t[-1] for t in RANGE_TESTS])
def test_normalize_lcc_range(raw, normed, name):
    assert normalize_lcc_range(*raw) == normed
