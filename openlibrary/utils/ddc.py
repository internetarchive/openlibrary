"""
Dewey Decimal Numbers

Known issues

## Further Reading
https://www.oclc.org/bibformats/en/0xx/082.html
"""
import re
from string import printable
from typing import Iterable, List

MULTIPLE_SPACES_RE = re.compile(r'\s+')
DDC_RE = re.compile(r'''
    (
        # Prefix
        (?P<prestar>\*)?  # Should be suffix
        (?P<neg>-)?  # Old standard; no longer used
        (?P<j>j)?  # Juvenile prefix
        C?  # Canadian CIP

        # The number
        (?P<number>\d{1,3}(\.+\s?\d+)?)

        # Suffix
        (?P<poststar>\*?)
        (?P<s>\s?s)?  # Series suffix
        (?P<B>\s?\[?B\]?)?  # Biographical
        (?P<ninetwo>\s(092|920|92))?  # No clue; shouldn't be its own DDC though
    )
    |
    (\[?(?P<fic>Fic|E)\.?\]?)
''', re.IGNORECASE | re.X)


def collapse_multiple_space(s: str) -> str:
    return MULTIPLE_SPACES_RE.sub(' ', s)


VALID_CHARS = set(printable) - set("/'′’,")


def normalize_ddc(ddc: str) -> List[str]:
    ddc = ''.join(
        char
        for char in collapse_multiple_space(ddc.strip())
        if char in VALID_CHARS)

    results: List[str] = []
    for match in DDC_RE.finditer(ddc):
        parts = match.groupdict()
        prefix = ''
        suffix = ''

        # DDCs should start at word boundaries
        start = match.start()
        if start > 0 and re.search(r'\b', ddc[start - 1]):
            continue
        # And end at them
        end = match.end()
        if end < len(ddc) and re.search(r'\b', ddc[end]):
            continue

        # Some old standard which isn't used anymore; might need to filter these
        # out, but they should sort OK so let's keep them.
        if parts['neg']:
            prefix += '-'
        # Juvenile prefix
        if parts['j']:
            prefix += 'j'

        # Star should be at end
        if parts['prestar'] or parts['poststar']:
            suffix = '*'
        # Series suffix
        if parts['s']:
            suffix += ' s'
        # Biographical
        if parts['B']:
            suffix += ' B'
        # Not at all sure
        if parts['ninetwo']:
            suffix += parts['ninetwo']

        # And now the actual number!
        if parts['number']:
            # Numbers in parenthesis are "series" numbers
            end = match.end('number')
            if end < len(ddc) and ddc[end] == ')':
                suffix += ' s'

            # pad the integer part of the number
            number_parts = parts['number'].split('.')
            integer = number_parts[0]

            # Copy decimal without losing precision
            decimal = '.' + number_parts[-1].strip() if len(number_parts) > 1 else ''

            number = '%03d%s' % (int(integer), decimal)

            # Discard catalog edition number
            # At least one classification number available
            if len(results) > 0:
                # Check if number is without decimal component
                if re.search(r'(^0?\d{1,2}$)', parts['number']):
                    continue

        # Handle [Fic] or [E]
        elif parts['fic']:
            number = '[%s]' % parts['fic'].title()
        else:
            continue

        results.append(prefix + number + suffix)

        # Include the non-j-prefixed form as well for correct sorting
        if prefix == 'j':
            results.append(number + suffix)

    return results


def normalize_ddc_range(start, end):
    """
    Normalizes the pieces of a lucene (i.e. solr)-style range.
    E.g. ('23.23', '*')
    :param str start:
    :param str end:

    >>> normalize_ddc_range('23.23', '*')
    ['023.23', '*']
    """

    ddc_range_norm = []
    for ddc in start, end:
        if ddc == '*':
            ddc_range_norm.append('*')
        else:
            normed = normalize_ddc(ddc)
            if normed:
                ddc_range_norm.append(normed[0])
            else:
                ddc_range_norm.append(None)
    return ddc_range_norm


def normalize_ddc_prefix(prefix: str) -> str:
    """
    Normalizes a DDC prefix to be used in searching. Integer prefixes are not modified

    >>> normalize_ddc_prefix('1')
    '1'
    >>> normalize_ddc_prefix('1.1')
    '001.1'
    """
    # 23.* should become 023*
    # 23.45* should become 023.45*
    if '.' in prefix:
        normed = normalize_ddc(prefix)
        return normed[0] if normed else prefix
    # 0* should stay as is
    # 23* should stay as is
    # j* should stay as is
    else:
        return prefix


def choose_sorting_ddc(normalized_ddcs: Iterable[str]) -> str:
    # Prefer unprefixed DDCs (so they sort correctly)
    preferred_ddcs = [ddc for ddc in normalized_ddcs if ddc[0] in '0123456789']
    # Choose longest; theoretically most precise?
    return sorted(preferred_ddcs or normalized_ddcs, key=len, reverse=True)[0]
