# bogo LRU
# does an O(n log n) cache rebuild every n insertions, so avg time = O(log n)
# should repace with an O(1) version which is a little more complicated

from itertools import count
class LRU(object):
    """
    >>> a = LRU(2)
    >>> a[1] = 3
    >>> a[2] = 5
    >>> a[3] = 7
    >>> a[4] = 9
    >>> a[5] = 11
    >>> assert (4 in a) and (5 in a)
    >>> assert (1 not in a) and (2 not in a) # these are aged out
    """
    def __init__(self, max_size = 1000):
        self.cache = {}
        self.max_size = max_size
        self.size = 0
        self.timestamp = count().next

    def __getitem__(self, key):
        a = self.__refresh(key)
        if a is not None:
            return a[1]
        raise KeyError

    def __contains__(self, key):
        return key in self.cache

    def __setitem__(self, key, value):
        a = self.__refresh(key)
        if a is not None:
            a[1] = value
        else:
            if len(self.cache) >= 2*self.max_size:
                # replace the cache with a new one containing only the
                # self.max_size newest entries.
                chopped = sorted(self.cache.iteritems(),
                                 key=(lambda (k,(ts,v)): ts),
                                 reverse=True)[:self.max_size]
                self.cache = dict(chopped)
            self.cache[key] = [self.timestamp(), value]
        
    def __refresh(self, key):
        a = self.cache.get(key)
        if a is not None:
            a[0] = self.timestamp()
        return a

def _test():
    import doctest
    doctest.testmod()

if __name__ == '__main__':
    _test()
