from typing import TYPE_CHECKING, Any, Final, NotRequired, TypedDict, cast

import web
from pydantic import TypeAdapter

from openlibrary.catalog.utils import (
    author_dates_match,
    flip_name,
    format_languages,
    key_int,
)
from openlibrary.core.helpers import extract_year
from openlibrary.utils import extract_numeric_id_from_olid, uniq

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


class AuthorImportDict(TypedDict):
    """Keys expected in the author import dict."""

    name: str
    personal_name: NotRequired[str]
    entity_type: NotRequired[str]
    remote_ids: NotRequired[dict]
    birth_date: NotRequired[str]
    death_date: NotRequired[str]
    date: NotRequired[str]
    title: NotRequired[str]


def do_flip(author: AuthorImportDict) -> None:
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


def pick_from_matches(author: AuthorImportDict, match: list["Author"]) -> "Author":
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


def find_author(author: AuthorImportDict) -> list["Author"]:
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

    def get_redirected_authors(authors: list["Author"]):
        keys = [a.type.key for a in authors]
        if any(k != '/type/author' for k in keys):
            seen: set[dict] = set()
            all_authors = [
                walk_redirects(a, seen) for a in authors if a['key'] not in seen
            ]
            return all_authors
        return authors

    # Look for OL ID first.
    if (key := author.get("key")) and (record := web.ctx.site.get(key)):
        # Always match on OL ID, even if remote identifiers don't match.
        return get_redirected_authors([record])

    # Try other identifiers next.
    if remote_ids := author.get("remote_ids"):
        queries = []
        matched_authors: list[Author] = []
        # Get all the authors that match any incoming identifier.
        for identifier, val in remote_ids.items():
            queries.append({"type": "/type/author", f"remote_ids.{identifier}": val})
        for query in queries:
            if reply := list(web.ctx.site.things(query)):
                matched_authors.extend(
                    get_redirected_authors(list(web.ctx.site.get_many(reply)))
                )
        matched_authors = uniq(matched_authors, key=lambda thing: thing.key)
        # The match is whichever one has the most identifiers in common
        if matched_authors:
            selected_match = sorted(
                matched_authors,
                key=lambda a: (
                    # First sort by number of matches desc
                    -1 * a.merge_remote_ids(remote_ids)[1],
                    # If there's a tie, prioritize lower OL ID
                    extract_numeric_id_from_olid(a.key),
                ),
            )[0]
            return [selected_match]

    # Fall back to name/date matching, which we did before introducing identifiers.
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
    things = []
    for query in queries:
        if reply := list(web.ctx.site.things(query)):
            things = get_redirected_authors(list(web.ctx.site.get_many(reply)))
            break
    match = []
    seen = set()
    for a in things:
        key = a['key']
        if key in seen:
            continue
        seen.add(key)
        assert a.type.key == '/type/author'
        if 'birth_date' in author and 'birth_date' not in a:
            continue
        if 'birth_date' not in author and 'birth_date' in a:
            continue
        if not author_dates_match(author, a):
            continue
        match.append(a)
    if not match:
        return []
    if len(match) == 1:
        return match
    return [pick_from_matches(author, match)]


def find_entity(author: AuthorImportDict) -> "Author | None":
    """
    Looks for an existing Author record in OL
    and returns it if found.

    :param dict author: Author import dict {"name": "Some One"}
    :return: Existing Author record if found, or None.
    """
    assert isinstance(author, dict)
    things = find_author(author)
    if "remote_ids" in author:
        for index, t in enumerate(things):
            t.remote_ids, _ = t.merge_remote_ids(author["remote_ids"])
            things[index] = t
    return things[0] if things else None


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


def author_import_record_to_author(
    author_import_record_dict: dict, eastern=False
) -> "Author | dict[str, Any]":
    """
    Converts an import style new-author dictionary into an
    Open Library existing author, or new author candidate, representation.
    Does NOT create new authors.

    :param dict author: Author import record {"name": "Some One"}
    :param bool eastern: Eastern name order
    :return: Open Library style Author representation, either existing Author with "key",
             or new candidate dict without "key".
    """
    TypeAdapter(AuthorImportDict).validate_python(author_import_record_dict)
    author_import_record = cast(AuthorImportDict, author_import_record_dict)
    if author_import_record.get('entity_type') != 'org' and not eastern:
        do_flip(author_import_record)
    if existing := find_entity(author_import_record):
        assert existing.type.key == '/type/author'
        for k in 'last_modified', 'id', 'revision', 'created':
            if existing.k:
                del existing.k
        new = existing
        if 'death_date' in author_import_record and 'death_date' not in existing:
            new['death_date'] = author_import_record['death_date']
        return new
    a: dict[str, Any] = {'type': {'key': '/type/author'}}
    for f in (
        'name',
        'title',
        'personal_name',
        'birth_date',
        'death_date',
        'date',
        'remote_ids',
    ):
        if f in author_import_record:
            a[f] = author_import_record[f]
    return a


type_map = {'description': 'text', 'notes': 'text', 'number_of_pages': 'int'}


def import_record_to_edition(rec: dict[str, Any]) -> dict[str, Any]:
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
                    book['authors'].append(
                        author_import_record_to_author(author, eastern=east)
                    )
            continue

        if k in ('languages', 'translated_from'):
            formatted_languages = format_languages(languages=v)
            book[k] = formatted_languages
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
