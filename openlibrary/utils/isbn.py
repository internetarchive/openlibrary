import re
import isbnlib
from isbnlib import canonical
import logging

logger = logging.getLogger("openlibrary")

def check_digit_10(isbn):
    """I believe this is checking the case where ISBNs start with a
    leading X? It only appears to be used in isbn_13_to_isbn_10 and
    isbn_10_to_isbn_13"""
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
    """I believe this is checking the case where ISBNs start with a
    leading X? It only appears to be used in isbn_13_to_isbn_10 and
    isbn_10_to_isbn_13"""
    if len(isbn) != 12:
        raise ValueError
    sum = 0
    for i in range(len(isbn)):
        c = int(isbn[i])
        if i % 2: w = 3
        else: w = 1
        sum += w * c
    r = 10 - (sum % 10)
    if r == 10:
        return '0'
    else:
        return str(r)

def isbn_13_to_isbn_10(isbn_13):
    isbn_13 = canonical(isbn_13)
    try:
        if len(isbn_13) != 13 or not isbn_13.isdigit()\
        or not isbn_13.startswith('978')\
        or check_digit_13(isbn_13[:-1]) != isbn_13[-1]:
            raise ValueError("%s is not a valid ISBN 13" % isbn_13)
    except ValueError as e:
        logger.info("Exception caught in ISBN transformation: %s" % e)
        return
    return isbn_13[3:-1] + check_digit_10(isbn_13[3:-1])

def isbn_10_to_isbn_13(isbn_10):
    isbn_10 = canonical(isbn_10)
    if len(isbn_10) == 13:
        return isbn_10
    try:
        if len(isbn_10) != 10 or not isbn_10[:-1].isdigit()\
        or check_digit_10(isbn_10[:-1]) != isbn_10[-1]:
            raise ValueError("%s is not a valid ISBN 10" % isbn_10)
    except ValueError as e:
        logger.info("Exception caught in ISBN transformation: %s" % e)
        return
    isbn_13 = '978' + isbn_10[:-1]
    return isbn_13 + check_digit_13(isbn_13)

def opposite_isbn(isbn): # ISBN10 -> ISBN13 and ISBN13 -> ISBN10
    for f in isbn_13_to_isbn_10, isbn_10_to_isbn_13:
        alt = f(canonical(isbn))
        if alt:
            return alt

def normalize_isbn(isbn):
    """removes spaces and dashes from isbn and ensures length

    XXX deprecated, just use isbnlib.canonical
    """
    return canonical(isbn)
