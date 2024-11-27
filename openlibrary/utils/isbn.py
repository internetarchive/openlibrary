from __future__ import annotations

from isbnlib import canonical


def check_digit_10(isbn):
    """Takes the first 9 digits of an ISBN10 and returns the calculated final checkdigit."""
    if len(isbn) != 9:
        raise ValueError("%s is not a valid ISBN 10" % isbn)
    sum = 0
    for i in range(len(isbn)):
        c = int(isbn[i])
        w = i + 1
        sum += w * c
    r = sum % 11
    if r == 10:
        return 'X'
    else:
        return str(r)


def check_digit_13(isbn):
    """Takes the first 12 digits of an ISBN13 and returns the calculated final checkdigit."""
    if len(isbn) != 12:
        raise ValueError
    sum = 0
    for i in range(len(isbn)):
        c = int(isbn[i])
        if i % 2:
            w = 3
        else:
            w = 1
        sum += w * c
    r = 10 - (sum % 10)
    if r == 10:
        return '0'
    else:
        return str(r)


def isbn_13_to_isbn_10(isbn_13: str) -> str | None:
    isbn_13 = canonical(isbn_13)
    if (
        len(isbn_13) != 13
        or not isbn_13.isdigit()
        or not isbn_13.startswith('978')
        or check_digit_13(isbn_13[:-1]) != isbn_13[-1]
    ):
        return None
    return isbn_13[3:-1] + check_digit_10(isbn_13[3:-1])


def isbn_10_to_isbn_13(isbn_10: str) -> str | None:
    isbn_10 = canonical(isbn_10)
    if (
        len(isbn_10) != 10
        or not isbn_10[:-1].isdigit()
        or check_digit_10(isbn_10[:-1]) != isbn_10[-1]
    ):
        return None
    isbn_13 = '978' + isbn_10[:-1]
    return isbn_13 + check_digit_13(isbn_13)


def to_isbn_13(isbn: str) -> str | None:
    """
    Tries to make an isbn into an isbn13; regardless of input isbn type
    """
    isbn = normalize_isbn(isbn) or isbn
    return isbn and (isbn if len(isbn) == 13 else isbn_10_to_isbn_13(isbn))


def opposite_isbn(isbn):  # ISBN10 -> ISBN13 and ISBN13 -> ISBN10
    for f in isbn_13_to_isbn_10, isbn_10_to_isbn_13:
        alt = f(canonical(isbn))
        if alt:
            return alt


def normalize_isbn(isbn: str) -> str | None:
    """
    Takes an isbn-like string, keeps only numbers and X/x, and returns an ISBN-like
    string or None.
    Does NOT validate length or checkdigits.
    """
    return isbn and canonical(isbn) or None


def get_isbn_10_and_13(isbn: str) -> tuple[str | None, str | None]:
    """
    Takes an ISBN 10 or 13 and returns an ISBN optional ISBN 10 and an ISBN 13,
    both in canonical form.
    """
    if canonical_isbn := normalize_isbn(isbn):
        isbn_13 = (
            canonical_isbn if len(canonical_isbn) == 13 else isbn_10_to_isbn_13(isbn)
        )
        isbn_10 = isbn_13_to_isbn_10(isbn_13) if isbn_13 else canonical_isbn
        return isbn_10, isbn_13

    return None, None


def normalize_identifier(
    identifier: str,
) -> tuple[str | None, str | None, str | None]:
    """
    Takes an identifier (e.g. an ISBN 10/13 or B* ASIN) and returns a tuple of:
        ASIN, ISBN_10, ISBN_13 or None, with the ISBNs in canonical form.
    """
    asin = identifier.upper() if identifier.upper().startswith("B") else None
    return asin, *get_isbn_10_and_13(identifier)


def get_isbn_10s_and_13s(isbns: str | list[str]) -> tuple[list[str], list[str]]:
    """
    Returns a tuple of list[isbn_10_strings], list[isbn_13_strings]

    Internet Archive stores ISBNs in a a string, or a list of strings,
    with no differentiation between ISBN 10 and ISBN 13. Open Library
    records need ISBNs in `isbn_10` and `isbn_13` fields.

    >>> get_isbn_10s_and_13s('1576079457')
    (['1576079457'], [])
    >>> get_isbn_10s_and_13s(['1576079457', '9781576079454', '1576079392'])
    (['1576079457', '1576079392'], ['9781576079454'])

    Notes:
        - this does no validation whatsoever--it merely checks length.
        - this assumes the ISBNs have no hyphens, etc.
    """
    isbn_10 = []
    isbn_13 = []

    # If the input is a string, it's a single ISBN, so put it in a list.
    isbns = [isbns] if isinstance(isbns, str) else isbns

    # Handle the list of ISBNs
    for isbn in isbns:
        isbn = isbn.strip()
        match len(isbn):
            case 10:
                isbn_10.append(isbn)
            case 13:
                isbn_13.append(isbn)

    return (isbn_10, isbn_13)
