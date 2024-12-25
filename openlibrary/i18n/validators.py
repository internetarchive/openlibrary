import re
from itertools import groupby

from babel.messages.catalog import (
    Catalog,
    Message,
)


def validate(message: Message, catalog: Catalog) -> list[str]:
    errors = [f'    {err}' for err in message.check(catalog)]
    if message.python_format and not message.pluralizable and message.string:
        errors.extend(_validate_cfmt(str(message.id or ''), str(message.string or '')))

    return errors


def _validate_cfmt(msgid: str, msgstr: str) -> list[str]:
    errors = []

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
    return {key: len(list(grp)) for key, grp in groupby(pieces)}


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

    return [m.group(0) for m in re.finditer(cfmt_re, string, flags=re.VERBOSE)]
