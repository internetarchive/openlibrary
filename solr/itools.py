# decorator to truncate a generator after the first n
# elements, useful for debugging

def slicer(n):
    from itertools import islice
    def s2(g):
        return lambda *a,**kw: islice(g(*a,**kw), n)
    return s2

# separate sequence into runs of size `runsize'
def runs(seq, runsize):
    from itertools import groupby, imap
    from operator import itemgetter
    snd = itemgetter(1)           # snd(tuple t) = second element of t
    for n,g in groupby(enumerate(seq),
                       lambda (n,s): n // runsize):
        yield imap(snd, g)

# chain together a sequence of sequences.  differs from
# itertools.chain in that seq itself is lazy-evaluated;
# for example, each seq element could open a file and
# return an iterator.

def ichain(seq):
    for s in seq:
        for i in s:
            yield i

# generate the sequence [f0, func(f0), func(func(f0)), ... ]
def iterate(func, f0):
    while True:
        yield f0
        f0 = func(f0)
