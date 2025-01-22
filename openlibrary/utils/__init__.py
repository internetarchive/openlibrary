"""Generic utilities"""

import re
from collections.abc import Callable, Iterable
from enum import Enum
from subprocess import CalledProcessError, run
from typing import Literal, TypeVar

to_drop = set(''';/?:@&=+$,<>#%"{}|\\^[]`\n\r''')


def str_to_key(s: str) -> str:
    """
    >>> str_to_key("?H$e##l{o}[0] -world!")
    'helo0_-world!'
    >>> str_to_key("".join(to_drop))
    ''
    >>> str_to_key("")
    ''
    """
    return ''.join(c if c != ' ' else '_' for c in s.lower() if c not in to_drop)


T = TypeVar('T')


def uniq(values: Iterable[T], key=None) -> list[T]:
    """Returns the unique entries from the given values in the original order.

    The value of the optional `key` parameter should be a function that takes
    a single argument and returns a key to test the uniqueness.
    TODO: Moved this to core/utils.py

    >>> uniq("abcbcddefefg")
    ['a', 'b', 'c', 'd', 'e', 'f', 'g']
    >>> uniq("011223344556677889")
    ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']
    """
    key = key or (lambda x: x)
    s = set()
    result = []
    for v in values:
        k = key(v)
        if k not in s:
            s.add(k)
            result.append(v)
    return result


def take_best(
    items: list[T],
    optimization: Literal["min", "max"],
    scoring_fn: Callable[[T], float],
) -> list[T]:
    """
    >>> take_best([], 'min', lambda x: x)
    []
    >>> take_best([3, 2, 1], 'min', lambda x: x)
    [1]
    >>> take_best([3, 4, 5], 'max', lambda x: x)
    [5]
    >>> take_best([4, 1, -1, -1], 'min', lambda x: x)
    [-1, -1]
    """
    best_score = float("-inf") if optimization == "max" else float("inf")
    besties = []
    for item in items:
        score = scoring_fn(item)
        if (optimization == "max" and score > best_score) or (
            optimization == "min" and score < best_score
        ):
            best_score = score
            besties = [item]
        elif score == best_score:
            besties.append(item)
        else:
            continue
    return besties


def multisort_best(
    items: list[T], specs: list[tuple[Literal["min", "max"], Callable[[T], float]]]
) -> T | None:
    """
    Takes the best item, taking into account the multisorts

    >>> multisort_best([], [])

    >>> multisort_best([3,4,5], [('max', lambda x: x)])
    5

    >>> multisort_best([
    ...     {'provider': 'ia', 'size': 4},
    ...     {'provider': 'ia', 'size': 12},
    ...     {'provider': None, 'size': 42},
    ... ], [
    ...     ('min', lambda x: 0 if x['provider'] == 'ia' else 1),
    ...     ('max', lambda x: x['size']),
    ... ])
    {'provider': 'ia', 'size': 12}
    """
    if not items:
        return None
    pool = items
    for optimization, fn in specs:
        # Shrink the pool down each time
        pool = take_best(pool, optimization, fn)
    return pool[0]


def dicthash(d):
    """Dictionaries are not hashable. This function converts dictionary into nested
    tuples, so that it can hashed.
    """
    if isinstance(d, dict):
        return tuple((k, dicthash(d[k])) for k in sorted(d))
    elif isinstance(d, list):
        return tuple(dicthash(v) for v in d)
    else:
        return d


olid_re = re.compile(r'OL\d+[A-Z]', re.IGNORECASE)


def find_olid_in_string(s: str, olid_suffix: str | None = None) -> str | None:
    """
    >>> find_olid_in_string("ol123w")
    'OL123W'
    >>> find_olid_in_string("/authors/OL123A/DAVIE_BOWIE")
    'OL123A'
    >>> find_olid_in_string("/authors/OL123A/DAVIE_BOWIE", "W")
    >>> find_olid_in_string("some random string")
    """
    found = re.search(olid_re, s)
    if not found:
        return None
    olid = found.group(0).upper()

    if olid_suffix and not olid.endswith(olid_suffix):
        return None

    return olid


def olid_to_key(olid: str) -> str:
    """
    >>> olid_to_key('OL123W')
    '/works/OL123W'
    >>> olid_to_key('OL123A')
    '/authors/OL123A'
    >>> olid_to_key('OL123M')
    '/books/OL123M'
    >>> olid_to_key("OL123L")
    '/lists/OL123L'
    """
    typ = {
        'A': 'authors',
        'W': 'works',
        'M': 'books',
        'L': 'lists',
    }[olid[-1]]
    if not typ:
        raise ValueError(f"Invalid olid: {olid}")
    return f"/{typ}/{olid}"


def extract_numeric_id_from_olid(olid):
    """
    >>> extract_numeric_id_from_olid("OL123W")
    '123'
    >>> extract_numeric_id_from_olid("/authors/OL123A")
    '123'
    """
    if '/' in olid:
        olid = olid.split('/')[-1]
    if olid.lower().startswith('ol'):
        olid = olid[2:]
    if not is_number(olid[-1].lower()):
        olid = olid[:-1]
    return olid


def is_number(s):
    """
    >>> all(is_number(n) for n in (1234, "1234", -1234, "-1234", 123.4, -123.4))
    True
    >>> not any(is_number(n) for n in ("123.4", "-123.4", "123a", "--1234"))
    True
    """
    try:
        int(s)
        return True
    except ValueError:
        return False


def get_software_version() -> str:
    """
    assert get_software_version()  # Should never return a falsy value
    """
    cmd = "git rev-parse --short HEAD --".split()
    try:
        return run(cmd, capture_output=True, text=True, check=True).stdout.strip()
    except CalledProcessError:
        return "unknown"


# See https://docs.python.org/3/library/enum.html#orderedenum
class OrderedEnum(Enum):
    def __ge__(self, other):
        if self.__class__ is other.__class__:
            return self.value >= other.value
        return NotImplemented

    def __gt__(self, other):
        if self.__class__ is other.__class__:
            return self.value > other.value
        return NotImplemented

    def __le__(self, other):
        if self.__class__ is other.__class__:
            return self.value <= other.value
        return NotImplemented

    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return self.value < other.value
        return NotImplemented
