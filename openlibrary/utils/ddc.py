"""
Dewey Decimal Numbers

Known issues

## Further Reading
https://www.oclc.org/bibformats/en/0xx/082.html
"""
import re

MULTIPLE_SPACES_RE = re.compile(r'\s+')
DDC_RE = re.compile(r'''
    (
        # Prefix
        (?P<prestar>\*)?  # Should be suffix
        (?P<neg>-)?  # Old standard; no longer used
        (?P<j>j)?  # Juvenile prefix
        C?  # Canadian CIP

        # The number
        (?P<number>\d{1,3}(\.\d+)?)

        # Suffix
        (?P<poststar>\*?)
        (?P<s>\s?s)?  # Series suffix
        (?P<B>\s?\[?B\]?)?  # Biographical
        (?P<ninetwo>\s920?)?  # No clue; shouldn't be its own DDC though
    )
    |
    (\[?(?P<fic>Fic|E)\.?\]?)
''', re.IGNORECASE | re.X)


def collapse_multiple_space(s):
    return MULTIPLE_SPACES_RE.sub(' ', s)


def normalize_ddc(ddc):
    """
    :param str ddc:
    :rtype: list of str
    """
    ddc = collapse_multiple_space(ddc.strip()).replace('/', '').replace("'", '')

    results = []
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
        if end < (len(ddc) - 1) and re.search(r'\b', ddc[end]):
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
            decimal = '.' + number_parts[1] if len(number_parts) > 1 else ''

            number = '%03d%s' % (int(integer), decimal)
        # Handle [Fic] or [E]
        elif parts['fic']:
            number = '[%s]' % parts['fic'].title()
        else:
            continue

        results.append(prefix + number + suffix)

    return results
