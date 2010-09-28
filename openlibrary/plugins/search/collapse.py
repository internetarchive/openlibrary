from itertools import groupby

def collapse_groups(page_numbers):
    """
    Given a list of page numbers, return a list of (pagenum, rdesc) pairs
    corresponding to ranges of consecutive page numbers.  For each range,
    pagenum is the first page number in the range, and rdesc is a string
    describing the range.

    >>> print collapse_groups([3,9,23,4,25,1,7,12,18,11,8,24,10])
    [(1, '1'), (3, '3-4'), (7, '7-12'), (18, '18'), (23, '23-25')]
    """

    # first use groupby to make an iterator whose elts are groups that
    # are consecutive by leaf number.
    # see  http://python.org/doc/lib/itertools-example.html
    # for another example of this construction

    g_iter = groupby(enumerate(sorted(page_numbers)),
                     lambda (i,n): i-n)

    # now flatten that iterator into a list of lists of leaf numbers
    groups = list(list(z for _, z in y) for _, y in g_iter)

    # finally, we'll make text strings for the leaf groups
    return list((g[0], collapse_one_group(g)) for g in groups)

def collapse_one_group(leaf_group):
    """collapse list of leaves into a single string, i.e.
    >>> collapse_one_group([2,3,4])
    '2-4'
    >>> collapse_one_group([85])
    '85'
    >>> # next example used to say 27-9, but we ditched that.
    >>> collapse_one_group([27,28,29])
    '27-29'
    >>> collapse_one_group([238,239,240,241])
    '238-241'
    >>> # don't say 280-5 any more either
    >>> collapse_one_group([280,281,282,283,284,285])
    '280-285'
    """
    # get the first and last leaf numbers in the group
    a,b = leaf_group[0], leaf_group[-1]

    # if there's just one leaf number, convert it, otherwise
    # convert the range.
    if a == b: return '%d'% a
    return '%d-%d' % (a,b)

if __name__ == '__main__':
    import doctest
    doctest.testmod()
