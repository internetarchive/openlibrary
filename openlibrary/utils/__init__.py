"""Generic utilities"""

from enum import Enum
import re
from subprocess import PIPE, Popen, STDOUT
from typing import TypeVar, Iterable, Literal, Callable, Optional

to_drop = set(''';/?:@&=+$,<>#%"{}|\\^[]`\n\r''')


def str_to_key(s):
    return ''.join(c if c != ' ' else '_' for c in s.lower() if c not in to_drop)


def finddict(dicts, **filters):
    """Find a dictionary that matches given filter conditions.

    >>> dicts = [{"x": 1, "y": 2}, {"x": 3, "y": 4}]
    >>> sorted(finddict(dicts, x=1).items())
    [('x', 1), ('y', 2)]
    """
    for d in dicts:
        if all(d.get(k) == v for k, v in filters.items()):
            return d


re_solr_range = re.compile(r'\[.+\bTO\b.+\]', re.I)
re_bracket = re.compile(r'[\[\]]')


def escape_bracket(q):
    if re_solr_range.search(q):
        return q
    return re_bracket.sub(lambda m: '\\' + m.group(), q)


T = TypeVar('T')


def uniq(values: Iterable[T], key=None) -> list[T]:
    """Returns the unique entries from the given values in the original order.

    The value of the optional `key` parameter should be a function that takes
    a single argument and returns a key to test the uniqueness.
    TODO: Moved this to core/utils.py
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
) -> Optional[T]:
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


author_olid_embedded_re = re.compile(r'OL\d+A', re.IGNORECASE)

def find_author_olid_in_string(s):
    """
    >>> find_author_olid_in_string("ol123a")
    'OL123A'
    >>> find_author_olid_in_string("/authors/OL123A/edit")
    'OL123A'
    >>> find_author_olid_in_string("some random string")
    """
    found = re.search(author_olid_embedded_re, s)
    return found and found.group(0).upper()


work_olid_embedded_re = re.compile(r'OL\d+W', re.IGNORECASE)

def find_work_olid_in_string(s):
    """
    >>> find_work_olid_in_string("ol123w")
    'OL123W'
    >>> find_work_olid_in_string("/works/OL123W/Title_of_book")
    'OL123W'
    >>> find_work_olid_in_string("some random string")
    """
    found = re.search(work_olid_embedded_re, s)
    return found and found.group(0).upper()


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
    try:
        int(s)
        return True
    except ValueError:
        return False


def get_software_version():  # -> str:
    cmd = "git rev-parse --short HEAD --".split()
    return str(Popen(cmd, stdout=PIPE, stderr=STDOUT).stdout.read().decode().strip())


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
