"""
Crash course Library of Congress Classification (LCC)

Examples:
 - HB1951 .R64 1995
 - DP402.C8 O46 1995
 - CS879 .R3 1995
 - NC248.S22 A4 1992
 - TJ563 .P66 1998
 - PQ3919.2.M2866 C83 1994
 - NA2500 .H64 1995
 - DT423.E26 9th.ed. 2012
 - PZ73.S758345255 2011
 - PZ8.3.G276Lo 1971

Has 3 parts:
 1. The class number: e.g. PQ3919.2 ; should match `[A-Z]{1,3}(\\d{1,4}(\\.\\d+)?)?`
 2. Cutter number(s): e.g. .M2866 C83
 3. Specification: Basically everything else, e.g. 2012, 9th.ed. 2012

### 1. The Class Number
The class number is what's used to determine the Library of Congress Subject. It has
a pretty well-defined structure, and should match `[A-Z]{1,3}(\\d{1,4}(\\.\\d+)?)?`

For example:
 - QH -> Biology
 - QH426-470 -> Genetics

_Note_: According to [1] (page 36), the first cutter is sometimes considered a part of
the class number. But this isn't discussed in [2], so it seems like it might not be
entirely well-defined.

### 2. Cutter Numbers
Cutter numbers are a somewhat phonetic hashing of a piece of "extra" information like
author last name, city, or whatever. Each character maps to a letter range, so for
example:
  - Idaho -> I33 -> I[d][a-d]
  - Campbell -> C36 -> C[a][m-o]

For the full mapping of character to letter ranges, see [1] Appendix B1 (page 355).

Because the number part of a cutter number maps to letters, even the numeral is sorted
lexicographically, so for example this is the correct sorting:
    [I2, I23, I3], **not** [I2, I3, I23]

In essence they are sort of sorted as if they were decimal numbers.

### 3. Specification

These aren't very well defined and could be just about anything. They usually include at
least the publication year of the edition, but might include edition numbers.

## Sorting

To get _fully_ sortable LCCs, you likely need to use a multipart scheme (as described in
[2]). That's not really feasible for our Solr instance (especially since we store info
at the work level, which likely has multiple LCCs). The added complexity of that
approach is also not immediately worth it right now (but might be in the future).

As a compromise, we make the class number and the first cutter sortable by making the
class number fixed-width. For example:
 - PZ73.S758345255 2011 -> PZ-0073.00000000.S758345255 2011
 - PZ8.3.G276Lo 1971    -> PZ-0008.30000000.G276Lo 1971

This allows for range queries that could include the first cutter. It sorts incorrectly
if:
  - The decimal of the class number is longer than 8 digits (few such cases in OL db)
  - The sort is determined by information that appears after the first cutter
  - The first cutter is a "double cutter", e.g. B945.D4B65 199

But it works for subject-related range queries, so we consider it sufficient.

## Further Reading

- Wagner, Scott etal. "A Comprehensive Approach to Algorithmic Machine Sorting of
    Library of Congress Call Numbers" (2019) [1]
- LCTS/CCS-PCC Task Force on  Library of Congress Classification Training. "Fundamentals
    of Library of Congress Classification" (????) [2]
- LCC subjects as PDFs https://www.loc.gov/catdir/cpso/lcco/
- LCC subjects "walkable" tree http://id.loc.gov/authorities/classification.html

## References

[1]: https://www.terkko.helsinki.fi/files/9666/classify_trnee_manual.pdf
[2]: https://ejournals.bc.edu/index.php/ital/article/download/11585/9839/
"""
import re
from typing import Iterable

from openlibrary.utils.ddc import collapse_multiple_space

LCC_PARTS_RE = re.compile(r'''
    ^
    # trailing dash only valid in "sortable" LCCs
    # Include W, even though technically part of NLM system
    (?P<letters>[A-HJ-NP-VWZ][A-Z-]{0,2})
    \s?
    (?P<number>\d{1,4}(\.\d+)?)?
    (?P<cutter1>[\s.][^\d\s\[]{1,3}\d*\S*)?
    (?P<rest>\s.*)?
    $
''', re.IGNORECASE | re.X)


def short_lcc_to_sortable_lcc(lcc):
    """
    See Sorting section of doc above
    :param str lcc: unformatted lcc
    :rtype: basestring|None
    """
    m = LCC_PARTS_RE.match(clean_raw_lcc(lcc))
    if not m:
        return None

    parts = m.groupdict()
    parts['letters'] = parts['letters'].upper().ljust(3, '-')
    parts['number'] = float(parts['number'] or 0)
    parts['cutter1'] = '.' + parts['cutter1'].lstrip(' .') if parts['cutter1'] else ''
    parts['rest'] = ' ' + parts['rest'].strip() if parts['rest'] else ''

    # There will often be a CPB Box No (whatever that is) in the LCC field;
    # E.g. "CPB Box no. 1516 vol. 17"
    # Although this might be useful to search by, it's not really an LCC,
    # so considering it invalid here.
    if parts['letters'] == 'CPB':
        return None

    return '%(letters)s%(number)013.8f%(cutter1)s%(rest)s' % parts


def sortable_lcc_to_short_lcc(lcc):
    """
    As close to the inverse of make_sortable_lcc as possible
    :param basestring lcc:
    :rtype: basestring
    """
    m = LCC_PARTS_RE.match(lcc)
    parts = m.groupdict()
    parts['letters'] = parts['letters'].strip('-')
    parts['number'] = parts['number'].strip('0').strip('.')  # Need to do in order!
    parts['cutter1'] = parts['cutter1'].strip(' ') if parts['cutter1'] else ''
    parts['rest'] = ' ' + parts['rest'].strip() if parts['rest'] else ''

    return '%(letters)s%(number)s%(cutter1)s%(rest)s' % parts


def clean_raw_lcc(raw_lcc):
    """
    Remove noise in lcc before matching to LCC_PARTS_RE
    :param basestring raw_lcc:
    :rtype: basestring
    """
    lcc = collapse_multiple_space(raw_lcc.replace('\\', ' ').strip(' '))
    if ((lcc.startswith('[') and lcc.endswith(']')) or
            (lcc.startswith('(') and lcc.endswith(')'))):
        lcc = lcc[1:-1]
    return lcc


def normalize_lcc_prefix(prefix):
    """
    :param str prefix: An LCC prefix
    :return: Prefix transformed to be a prefix for sortable LCC
    :rtype: str|None
    """
    if re.match(r'^[A-Z]+$', prefix, re.I):
        return prefix
    else:
        # A123* should be normalized to A--0123*
        # A123.* should be normalized to A--0123.*
        # A123.C* should be normalized to A--0123.00000000.C*
        lcc_norm = short_lcc_to_sortable_lcc(prefix.rstrip('.'))
        if lcc_norm:
            result = lcc_norm.rstrip('0')
            if '.' in prefix and prefix.endswith('0'):
                zeros_to_add = len(prefix) - len(prefix.rstrip('0'))
                result += '0' * zeros_to_add
            return result.rstrip('.')
        else:
            return None


def normalize_lcc_range(start, end):
    """
    :param str start: LCC prefix to start range
    :param str end: LCC prefix to end range
    :return: range with prefixes being prefixes for sortable LCCs
    :rtype: [str, str]
    """
    return [
        lcc if lcc == '*' else short_lcc_to_sortable_lcc(lcc)
        for lcc in (start, end)
    ]


def choose_sorting_lcc(sortable_lccs: Iterable[str]) -> str:
    # Choose longest; theoretically most precise?
    # Note we go to short-form first, so eg 'A123' beats 'A'
    def short_len(lcc: str) -> int:
        return len(sortable_lcc_to_short_lcc(lcc))
    return sorted(sortable_lccs, key=short_len, reverse=True)[0]
