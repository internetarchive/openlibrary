from itertools import groupby
import re
from typing import List

from babel.messages.catalog import TranslationError, Message, Catalog
from babel.messages.checkers import python_format


def validate(message: Message, catalog: Catalog) -> List[str]:
    errors = _validate_fuzzy(message)
    errors.extend(_validate_format(message, catalog))
    errors.extend(_validate_cfmt(message.id, message.string))

    return errors


def _validate_format(message: Message, catalog: Catalog) -> List[str]:
    """Returns an error list if the format strings are mismatched.

    Relies on Babel's built-in python format checker.
    """
    errors = []

    if message.python_format:
        try:
            python_format(catalog, message)
        except TranslationError as e:
            errors.append(f'    {e}')

    return errors


def _validate_fuzzy(message: Message) -> List[str]:
    """Returns an error list if the message is fuzzy.

    If a fuzzy flag is found above the header of a `.po`
    file, the message will have `None` as its line number.
    """
    errors = []
    if message.fuzzy:
        if message.lineno:
            errors.append('    Is fuzzy')
        else:
            errors.append(
                'File is fuzzy.  Remove line containing "#, fuzzy"'
                ' found near the beginning of the file.'
            )

    return errors


def _validate_cfmt(msgid: str, msgstr: str) -> List[str]:
    errors = []

    if len(msgstr) and isinstance(msgstr, str):
        if _cfmt_fingerprint(msgid) != _cfmt_fingerprint(msgstr):
            errors.append('    Failed custom string format validation')

    return errors


def _cfmt_fingerprint(string: str):
    """
    Get a fingerprint dict of the cstyle format in this string
    >>> _cfmt_fingerprint('hello %s')
    {'%s': 1}
    >>> _cfmt_fingerprint('hello %s and %s')
    {'%s': 2}
    >>> _cfmt_fingerprint('hello %(title)s. %(first)s %(last)s')
    {'%(title)s': 1, '%(first)s': 1, '%(last)s': 1}
    """
    pieces = _parse_cfmt(string)
    return {
        key: len(list(grp))
        for key, grp in groupby(pieces)
    }


def _parse_cfmt(string: str):
    """
    Extract e.g. '%s' from cstyle python format strings
    >>> _parse_cfmt('hello %s')
    ['%s']
    >>> _parse_cfmt(' by %(name)s')
    ['%(name)s']
    >>> _parse_cfmt('%(count)d Lists')
    ['%(count)d']
    >>> _parse_cfmt('100%% Complete!')
    ['%%']
    >>> _parse_cfmt('%(name)s avez %(count)s listes.')
    ['%(name)s', '%(count)s']
    >>> _parse_cfmt('')
    []
    >>> _parse_cfmt('Hello World')
    []
    """
    cfmt_re = r'''
        (
            %(?:
                (?:\([a-zA-Z_][a-zA-Z0-9_]*?\))?   # e.g. %(blah)s
                (?:[-+0 #]{0,5})                   # optional flags
                (?:\d+|\*)?                        # width
                (?:\.(?:\d+|\*))?                  # precision
                (?:h|l|ll|w|I|I32|I64)?            # size
                [cCdiouxXeEfgGaAnpsSZ]             # type
            )
        )
        |                                # OR
        %%                               # literal "%%"
    '''

    return [
        m.group(0)
        for m in re.finditer(cfmt_re, string, flags=re.VERBOSE)
    ]
