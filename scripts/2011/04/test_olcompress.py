"""OL uses a custom compression in storing objects in memcache.

This programs tests the effectiveness of that compression aginst regular compression.
"""
import urllib
import zlib
from openlibrary.utils import olcompress
import random
import simplejson

def wget(url):
    return urllib.urlopen(url).read()

def do_compress(text):
    c1 = zlib.compress(text)

    compress = olcompress.OLCompressor().compress
    c2 = compress(text)

    return len(text), len(c1), len(c2)
    
def test_url(label, url):
    name = url.split("/")[-1]
    text = wget(url)
    x0, x1, x2 = do_compress(text)
    improvement = (x1-x2)/float(x1) * 100
    cols = label, name, x0, x1, x2, improvement
    print "\t".join(str(c) for c in cols)
    return x1, x2
    
def test_random_pattern(label, pattern, max, count):
    return [
        test_url(label, pattern % random.randint(1, max))
        for i in range(count)
    ]
    
def test_recent_lists():
    def get_list_urls():
        json = wget('http://openlibrary.org/recentchanges/lists.json?limit=10')
        d = simplejson.loads(json)

        for change in d:
            key = change.get("data", {}).get("list", {}).get("key")
            if key:
                yield "http://openlibrary.org/" + key + ".json"
    
    return [test_url("list", url) for url in get_list_urls()]

def main():
    d1 = test_random_pattern("book", "http://openlibrary.org/books/OL%dM.json", 2000000, 10)
    d2 = test_random_pattern("work", "http://openlibrary.org/works/OL%dW.json", 1000000, 10)
    d3 = test_random_pattern("author", "http://openlibrary.org/authors/OL%dA.json", 600000, 10)
    d4 = test_recent_lists()
        
    d = d1+d2+d3+d4
    x1 = sum(x[0] for x in d)
    x2 = sum(x[1] for x in d)
    
    improvement = (x1-x2)/float(x1) * 100
    
    print
    print "Overall improvement", improvement
    
    
if __name__ == "__main__":
    main()
