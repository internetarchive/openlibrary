from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from babel.messages.catalog import (
        Catalog,
        Message,
    )


def validate(message: Message, catalog: Catalog) -> list[str]:
    errors = [f"    {err}" for err in message.check(catalog)]
    if message.python_format and not message.pluralizable and message.string:
        errors.extend(_validate_cfmt(str(message.id or ""), str(message.string or "")))
    errors.extend(_validate_substitution(message))

    return errors


def _validate_cfmt(msgid: str, msgstr: str) -> list[str]:
    errors = []

    if _cfmt_fingerprint(msgid) != _cfmt_fingerprint(msgstr):
        errors.append("    Failed custom string format validation")

    return errors


def _cfmt_fingerprint(string: str) -> tuple[tuple[str, ...], frozenset[str]]:
    """
    Get a fingerprint of the cstyle format in this string: positional placeholders in
    order, since `%` consumes them in sequence, and the set of everything else, since
    named placeholders are looked up by key and may be reordered or repeated.
    >>> _cfmt_fingerprint('hello %s and %d')
    (('%s', '%d'), frozenset())
    >>> _cfmt_fingerprint('hello %s and %d') == _cfmt_fingerprint('%d and %s')
    False
    >>> _cfmt_fingerprint('%(username)s read %(total)d. Join %(username)s') == _cfmt_fingerprint('%(total)d read by %(username)s')
    True
    """
    pieces = _parse_cfmt(string)
    positional = tuple(p for p in pieces if p != "%%" and not p.startswith("%("))
    return positional, frozenset(p for p in pieces if p == "%%" or p.startswith("%("))


# Conversions that raise on a str argument; `s` accepts anything.
NUMERIC_CONVERSIONS = frozenset("cdiouxXeEfFgG")


def _format_args(msgids: list[str]) -> dict | tuple | None:
    """
    Arguments shaped the way the msgid declares them: a str for `%s`, an int for `%d`.
    >>> _format_args(['by <a href="%s">You</a>'])
    ('x',)
    >>> _format_args(['%(count)d item', '%(count)d items'])
    {'count': 1}
    >>> _format_args(['100%% Complete!']) is None
    True
    """
    named: dict = {}
    positional: list = []
    for msgid in msgids:
        values = []
        for placeholder in _parse_cfmt(msgid):
            if placeholder == "%%":
                continue
            value = 1 if placeholder[-1] in NUMERIC_CONVERSIONS else "x"
            if placeholder.startswith("%("):
                named[placeholder[2 : placeholder.index(")")]] = value
            else:
                values.append(value)
        positional = max(positional, values, key=len)
    if named:
        return named
    return tuple(positional) or None


def _validate_substitution(message: Message) -> list[str]:
    """
    Apply every translated form to the arguments its msgid accepts, the way
    GetText and ungettext do at render time with no try/except. Unlike
    _validate_cfmt this covers plural forms, and unlike Babel's checker it catches
    malformed conversions such as `%(count)개`, which Babel reads as "no placeholders".
    """
    msgids = [str(m) for m in message.id] if message.pluralizable else [str(message.id or "")]
    args = _format_args(msgids)
    if args is None:
        return []
    msgstrs = message.string if message.pluralizable else [message.string]
    errors = []
    for msgstr in msgstrs:
        if not msgstr:
            continue
        try:
            msgstr % args
        except (TypeError, ValueError, KeyError) as e:
            errors.append(f"    {msgstr!r} % {args!r} raises {type(e).__name__}: {e}")
    return errors


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
    cfmt_re = r"""
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
    """

    return [m.group(0) for m in re.finditer(cfmt_re, string, flags=re.VERBOSE)]
