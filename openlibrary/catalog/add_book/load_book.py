from typing import TYPE_CHECKING, Any, Final

import web

from openlibrary.catalog.utils import author_dates_match, flip_name, key_int
from openlibrary.core.helpers import extract_year

if TYPE_CHECKING:
    from openlibrary.plugins.upstream.models import Author


# Sort by descending length to remove the _longest_ match.
# E.g. remove "señorita" and not "señor", when both match.
HONORIFICS: Final = sorted(
    [
        'countess',
        'doctor',
        'doktor',
        'dr',
        'dr.',
        'frau',
        'fräulein',
        'herr',
        'lady',
        'lord',
        'm.',
        'madame',
        'mademoiselle',
        'miss',
        'mister',
        'mistress',
        'mixter',
        'mlle',
        'mlle.',
        'mme',
        'mme.',
        'monsieur',
        'mr',
        'mr.',
        'mrs',
        'mrs.',
        'ms',
        'ms.',
        'mx',
        'mx.',
        'professor',
        'señor',
        'señora',
        'señorita',
        'sir',
        'sr.',
        'sra.',
        'srta.',
    ],
    key=lambda x: len(x),
    reverse=True,
)

HONORIFC_NAME_EXECPTIONS = frozenset(
    {
        "dr. seuss",
        "dr seuss",
        "dr oetker",
        "doctor oetker",
    }
)


def east_in_by_statement(rec: dict[str, Any], author: dict[str, Any]) -> bool:
    """
    Returns False if there is no by_statement in rec.
    Otherwise returns whether author name uses eastern name order.
    TODO: elaborate on what this actually means, and how it is used.
    """
    if 'by_statement' not in rec:
        return False
    if 'authors' not in rec:
        return False
    name = author['name']
    flipped = flip_name(name)
    name = name.replace('.', '')
    name = name.replace(', ', '')
    if name == flipped.replace('.', ''):
        # name was not flipped
        return False
    return rec['by_statement'].find(name) != -1


def do_flip(author: dict[str, Any]) -> None:
    """
    Given an author import dict, flip its name in place
    i.e. Smith, John => John Smith
    """
    if 'personal_name' in author and author['personal_name'] != author['name']:
        # Don't flip names if name is more complex than personal_name (legacy behaviour)
        return
    first_comma = author['name'].find(', ')
    if first_comma == -1:
        return
    # e.g: Harper, John Murdoch, 1845-
    if author['name'].find(',', first_comma + 1) != -1:
        return
    if author['name'].find('i.e.') != -1:
        return
    if author['name'].find('i. e.') != -1:
        return
    name = flip_name(author['name'])
    author['name'] = name
    if 'personal_name' in author:
        author['personal_name'] = name


def pick_from_matches(author: dict[str, Any], match: list["Author"]) -> "Author":
    """
    Finds the best match for author from a list of OL authors records, match.

    :param dict author: Author import representation
    :param list match: List of matching OL author records
    :rtype: dict
    :return: A single OL author record from match
    """
    maybe = []
    if 'birth_date' in author and 'death_date' in author:
        maybe = [m for m in match if 'birth_date' in m and 'death_date' in m]
    elif 'date' in author:
        maybe = [m for m in match if 'date' in m]
    if not maybe:
        maybe = match
    if len(maybe) == 1:
        return maybe[0]
    return min(maybe, key=key_int)


def find_author(author: dict[str, Any]) -> list["Author"]:
    """
    Searches OL for an author by a range of queries.
    """

    def walk_redirects(obj, seen):
        seen.add(obj['key'])
        while obj['type']['key'] == '/type/redirect':
            assert obj['location'] != obj['key']
            obj = web.ctx.site.get(obj['location'])
            seen.add(obj['key'])
        return obj

    # Try for an 'exact' (case-insensitive) name match, but fall back to alternate_names,
    # then last name with identical birth and death dates (that are not themselves `None` or '').
    name = author["name"].replace("*", r"\*")
    queries = [
        {"type": "/type/author", "name~": name},
        {"type": "/type/author", "alternate_names~": name},
        {
            "type": "/type/author",
            "name~": f"* {name.split()[-1]}",
            "birth_date~": f"*{extract_year(author.get('birth_date', '')) or -1}*",
            "death_date~": f"*{extract_year(author.get('death_date', '')) or -1}*",
        },  # Use `-1` to ensure an empty string from extract_year doesn't match empty dates.
    ]
    for query in queries:
        if reply := list(web.ctx.site.things(query)):
            break

    authors = [web.ctx.site.get(k) for k in reply]
    if any(a.type.key != '/type/author' for a in authors):
        seen: set[dict] = set()
        authors = [walk_redirects(a, seen) for a in authors if a['key'] not in seen]
    return authors


def find_entity(author: dict[str, Any]) -> "Author | None":
    """
    Looks for an existing Author record in OL
    and returns it if found.

    :param dict author: Author import dict {"name": "Some One"}
    :return: Existing Author record if found, or None.
    """
    assert isinstance(author, dict)
    things = find_author(author)
    if author.get('entity_type', 'person') != 'person':
        return things[0] if things else None
    match = []
    seen = set()
    for a in things:
        key = a['key']
        if key in seen:
            continue
        seen.add(key)
        orig_key = key
        assert a.type.key == '/type/author'
        if 'birth_date' in author and 'birth_date' not in a:
            continue
        if 'birth_date' not in author and 'birth_date' in a:
            continue
        if not author_dates_match(author, a):
            continue
        match.append(a)
    if not match:
        return None
    if len(match) == 1:
        return match[0]
    return pick_from_matches(author, match)


def remove_author_honorifics(name: str) -> str:
    """
    Remove honorifics from an author's name field.

    If the author's name is only an honorific, it will return the original name.
    """
    if name.casefold() in HONORIFC_NAME_EXECPTIONS:
        return name

    if honorific := next(
        (
            honorific
            for honorific in HONORIFICS
            if name.casefold().startswith(f"{honorific} ")  # Note the trailing space.
        ),
        None,
    ):
        return name[len(f"{honorific} ") :].lstrip() or name
    return name


def import_author(author: dict[str, Any], eastern=False) -> "Author | dict[str, Any]":
    """
    Converts an import style new-author dictionary into an
    Open Library existing author, or new author candidate, representation.
    Does NOT create new authors.

    :param dict author: Author import record {"name": "Some One"}
    :param bool eastern: Eastern name order
    :return: Open Library style Author representation, either existing Author with "key",
             or new candidate dict without "key".
    """
    assert isinstance(author, dict)
    if author.get('entity_type') != 'org' and not eastern:
        do_flip(author)
    if existing := find_entity(author):
        assert existing.type.key == '/type/author'
        for k in 'last_modified', 'id', 'revision', 'created':
            if existing.k:
                del existing.k
        new = existing
        if 'death_date' in author and 'death_date' not in existing:
            new['death_date'] = author['death_date']
        return new
    a = {'type': {'key': '/type/author'}}
    for f in 'name', 'title', 'personal_name', 'birth_date', 'death_date', 'date':
        if f in author:
            a[f] = author[f]
    return a


class InvalidLanguage(Exception):
    def __init__(self, code):
        self.code = code

    def __str__(self):
        return f"invalid language code: '{self.code}'"


type_map = {'description': 'text', 'notes': 'text', 'number_of_pages': 'int'}


def build_query(rec: dict[str, Any]) -> dict[str, Any]:
    """
    Takes an edition record dict, rec, and returns an Open Library edition
    suitable for saving.
    :return: Open Library style edition dict representation
    """
    book: dict[str, Any] = {
        'type': {'key': '/type/edition'},
    }
    for k, v in rec.items():
        if k == 'authors':
            if v and v[0]:
                book['authors'] = []
                for author in v:
                    author['name'] = remove_author_honorifics(author['name'])
                    east = east_in_by_statement(rec, author)
                    book['authors'].append(import_author(author, eastern=east))
            continue
        if k in ('languages', 'translated_from'):
            for language in v:
                if web.ctx.site.get('/languages/' + language.lower()) is None:
                    raise InvalidLanguage(language.lower())
            book[k] = [{'key': '/languages/' + language.lower()} for language in v]
            continue
        if k in type_map:
            t = '/type/' + type_map[k]
            if isinstance(v, list):
                book[k] = [{'type': t, 'value': i} for i in v]
            else:
                book[k] = {'type': t, 'value': v}
        else:
            book[k] = v
    return book
