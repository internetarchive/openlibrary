def basic_strip_stopwords(q):
    """Strip stopwords from an all-alphabetic query, needed to avoid some bugs
    in the php basic query expander.  do something more sensible later @@
    
    >>> print basic_strip_stopwords('soul of man')
    soul man
    >>> print basic_strip_stopwords('Rubber soul')
    Rubber soul
    >>> print basic_strip_stopwords('title:(soul of man)')
    title:(soul of man)
    """
    
    # standard list of Lucene stopwords, from solr distribution
    stopwords = set("""an and are as at be but by for if in into is it no
    not of on or s such t that the their then there these they this to
    was will with""".split())

    w = q.strip().split()
    if all(all(map(str.isalpha, a)) for a in w):
        return ' '.join(a for a in w if a not in stopwords)
    else:
        return q

if __name__ == '__main__':
    import doctest
    doctest.testmod()
