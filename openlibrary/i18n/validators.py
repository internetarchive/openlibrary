from __future__ import annotations

import gettext
import re
from typing import TYPE_CHECKING

from babel.messages.catalog import PYTHON_FORMAT, Message

if TYPE_CHECKING:
    from babel.messages.catalog import Catalog


def validate(message: Message, catalog: Catalog) -> list[str]:
    errors = [f"    {err}" for err in message.check(catalog)]
    if errors and message.pluralizable and _form0_selected_beyond_one(catalog) and _form0_may_carry_plural_placeholders(message):
        # msgstr[0] is also shown for some n other than 1 (every n with nplurals=1,
        # n=21, 31, ... in ru/uk/hr), so it may answer to msgid_plural, the English it
        # stands in for there. Babel's check compares it only with the singular msgid.
        as_plural = Message((message.id[1], message.id[1]), message.string, flags=message.flags, context=message.context)
        if not as_plural.check(catalog):
            errors = []
    if message.python_format and not message.pluralizable and message.string:
        errors.extend(_validate_cfmt(str(message.id or ""), str(message.string or "")))
    if message.fuzzy:
        pass  # left out of the compiled .mo, so never rendered
    elif _browser_only(message):
        errors.extend(f"    {err}" for err in _unknown_browser_placeholders(message))
        errors.extend(_validate_braces(message))
    else:
        errors.extend(f"    {err}" for err in _substitution_errors(message))

    return errors


def render_errors(message: Message) -> list[str]:
    """
    What would go wrong rendering this translation badly enough that
    ``install_translations`` keeps the language's committed file instead: Python
    raising when it fills the translation in, or JavaScript leaving a placeholder
    empty. ``validate`` runs the same checks with stricter stand-in values, so a
    translation it accepts is never refused at deploy.
    """
    if _browser_only(message):
        return _unknown_browser_placeholders(message)
    return _substitution_errors(message, numbers_only=True)


def _browser_only(message: Message) -> bool:
    """
    Whether only JavaScript uses this string, judged by where it was extracted from.
    i18n.js fills in a browser string's placeholders itself and never applies Python's
    `%`, so a literal `%` in it ("{percentage}%") is just a percent sign. A string that
    a template or Python file also uses is checked as a Python string.
    """
    return bool(message.locations) and all(filename.endswith((".js", ".vue")) for filename, _lineno in message.locations)


# The placeholders JavaScript fills in: `{name}` (the Lit components' label templates,
# which use this same pattern) and `%(name)s` / `%(name)d` (`fmt()` in i18n.js).
BRACE_RE = re.compile(r"\{(\w+)\}")
BROWSER_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}|%\((\w+)\)[sd]")


def _browser_placeholders(s: str) -> set[str]:
    """
    >>> sorted(_browser_placeholders("{name}: %(count)s, {name} again"))
    ['count', 'name']
    """
    return {brace or named for brace, named in BROWSER_PLACEHOLDER_RE.findall(s)}


def _unknown_browser_placeholders(message: Message) -> list[str]:
    """
    Placeholders in a browser string's translation that the code will not fill in.
    JavaScript replaces a name it has no value for with an empty string, so "{nombre}"
    where the English says "{name}" shows users a label with the name missing.
    """
    msgids = [str(m) for m in message.id] if message.pluralizable else [str(message.id or "")]
    expected = set().union(*map(_browser_placeholders, msgids))
    msgstrs = message.string if message.pluralizable else [message.string]
    errors = []
    for msgstr in msgstrs:
        if unknown := _browser_placeholders(msgstr or "") - expected:
            errors.append(f"{msgstr!r} uses {', '.join(sorted(unknown))}, which the English does not have")
    return errors


def _validate_braces(message: Message) -> list[str]:
    """
    A singular browser string's translation has the same {name} placeholders as its
    msgid, the rule _validate_cfmt applies to %(name)s: one that drops {percentage}
    shows users a label without the number. Plural forms may drop one, as a singular
    form often drops the count, so they only get _unknown_browser_placeholders.
    """
    if message.pluralizable or not message.string:
        return []
    expected, actual = (set(BRACE_RE.findall(str(s))) for s in (message.id, message.string))
    if expected == actual:
        return []
    missing, extra = expected - actual, actual - expected
    if missing and not extra:
        return [f"    {message.string!r} leaves out {{{'}, {'.join(sorted(missing))}}}"]
    # `extra` is reported by _unknown_browser_placeholders
    return []


PAREN_PLURAL_RE = re.compile(r"\w\((?:s|es)\)")


def check_source_string(msgid: str) -> list[str]:
    """
    Problems in an English msgid that translators can't work around: a language that
    needs the values in another order can't reorder bare `%s`, and "item(s)" has no
    correct form in languages with several plurals.
    >>> check_source_string("Showing %(shown)s of %(total)s results")
    []
    >>> check_source_string("See %s book")
    []
    >>> check_source_string("%(percent)s%% done, goal %(goal)s%%")
    []
    >>> check_source_string("Showing %s of %s results")
    ['2 unnamed placeholders (%s, %s): name them, e.g. %(count)s, so translators can reorder them']
    >>> check_source_string("Re-queued %(count)d failed item(s).")
    ['"item(s)" is not a plural: use ungettext() with singular and plural strings']
    """
    problems = []
    unnamed = [p for p in _parse_cfmt(msgid) if p != "%%" and not p.startswith("%(")]
    if len(unnamed) > 1:
        problems.append(f"{len(unnamed)} unnamed placeholders ({', '.join(unnamed)}): name them, e.g. %(count)s, so translators can reorder them")
    if m := PAREN_PLURAL_RE.search(msgid):
        word = msgid[: m.end()].rsplit(maxsplit=1)[-1]
        problems.append(f'"{word}" is not a plural: use ungettext() with singular and plural strings')
    return problems


def _form0_selected_beyond_one(catalog: Catalog) -> bool:
    try:
        rule = gettext.c2py(catalog.plural_expr)
        return any(rule(n) == 0 for n in range(1000) if n != 1)
    except ValueError, ArithmeticError:
        # A rule gettext cannot evaluate: keep the singular-only check.
        return False


def _form0_may_carry_plural_placeholders(message: Message) -> bool:
    """
    msgstr[0] holds every placeholder of the singular, nothing outside the two msgids,
    and msgid_plural brings something the singular lacks. Without that last clause a
    placeholder-free msgid_plural would turn Babel's check off entirely.
    """
    singular, plural = (str(m) for m in message.id)
    form0 = str(message.string[0] if message.string else "")

    # Babel's own placeholder syntax, so %r and %F count as placeholders here as they
    # do in the check being forgiven.
    def placeholders(s: str) -> list[str | None]:
        return [m.group(1) for m in PYTHON_FORMAT.finditer(s) if m.group(3) != "%"]

    def positional(s: str) -> int:
        return sum(1 for name in placeholders(s) if name is None)

    def names(s: str) -> set[str]:
        return {name for name in placeholders(s) if name is not None}

    sing_n, plur_n, form_n = (names(s) for s in (singular, plural, form0))
    mixed_kinds = (positional(singular) and plur_n) or (sing_n and positional(plural))
    brings_more = bool(plur_n - sing_n) or positional(plural) > positional(singular)
    # The last two clauses are also enforced by Babel's check against msgid_plural;
    # they are kept so this rule does not rest on Babel's internals.
    return not mixed_kinds and brings_more and sing_n <= form_n and form_n <= sing_n | plur_n and positional(form0) in {positional(singular), positional(plural)}


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


def _format_args(msgids: list[str], *, numbers_only: bool = False) -> dict | tuple:
    """
    Arguments shaped the way the msgid declares them: a str for `%s`, an int for `%d`.
    The str is two characters long because `%c` accepts one. With numbers_only every
    value is an int, which `%s`, `%d` and `%f` all accept: the deploy check refuses
    only translations that raise whatever the value, while validate also flags a `%d`
    whose msgid passes a str. A msgid with no placeholders gets {}, because Jinja's
    newstyle gettext applies `% variables` even when there are none.
    >>> _format_args(['by <a href="%s">You</a>'])
    ('xx',)
    >>> _format_args(['by <a href="%s">You</a>'], numbers_only=True)
    (1,)
    >>> _format_args(['%(count)d item', '%(count)d items'])
    {'count': 1}
    >>> _format_args(['100%% Complete!'])
    {}
    """
    named: dict = {}
    positional: list = []
    for msgid in msgids:
        values = []
        for placeholder in _parse_cfmt(msgid):
            if placeholder == "%%":
                continue
            value = 1 if numbers_only or placeholder[-1] in NUMERIC_CONVERSIONS else "xx"
            if placeholder.startswith("%("):
                named[placeholder[2 : placeholder.index(")")]] = value
            else:
                values.append(value)
        positional = max(positional, values, key=len)
    if named:
        return named
    return tuple(positional) or {}


def _substitution_errors(message: Message, *, numbers_only: bool = False) -> list[str]:
    """
    Apply every translated form to the arguments its msgid accepts, the way GetText,
    ungettext and Jinja do at render time with no try/except. Unlike _validate_cfmt
    this covers plural forms, and unlike Babel's checker it catches malformed
    conversions such as `%(count)개`, which Babel reads as "no placeholders", and a
    bare `%` in a translation whose msgid has no placeholders.
    """
    msgids = [str(m) for m in message.id] if message.pluralizable else [str(message.id or "")]
    args = _format_args(msgids, numbers_only=numbers_only)
    msgstrs = message.string if message.pluralizable else [message.string]
    errors = []
    for msgstr in msgstrs:
        if not msgstr:
            continue
        try:
            msgstr % args
        except (TypeError, ValueError, KeyError) as e:
            errors.append(f"{msgstr!r} % {args!r} raises {type(e).__name__}: {e}")
            continue
        if isinstance(args, dict) and any(p != "%%" and not p.startswith("%(") for p in _parse_cfmt(msgstr)):
            # A mapping fills a positional placeholder with its own repr instead of raising
            errors.append(f"{msgstr!r} uses positional placeholders but its msgid has none")
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
