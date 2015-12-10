#! /bin/bash
"""Script to findout the amount of memory required to cache all OL data.
"""

import random
import web
import simplejson
from openlibrary.utils import olcompress

works = 15000000
editions = 25000000
authors = 6000000

compressor = olcompress.OLCompressor()

N = 100

def clen(d):
    """Computes the compressed length of given data."""
    return len(compressor.compress(simplejson.dumps(d)))

def get_sizes(label, pattern, max, count):
    # there might not be docs for some numbers. 
    # Considering double keys than required and skipping the None
    keys = [pattern % random.randint(0, max) for i in range(2*count)]
    docs = [doc for doc in web.ctx.site.get_many(keys) if doc][:count]

    overheads = 48 + 20 # item size and key size

    doc_size = overheads + sum(clen(doc.dict()) for doc in docs) / len(docs)
    data_size = overheads + sum(clen(doc._get_d()) for doc in docs) / len(docs)
    M = 1000000

    total_doc_size = doc_size*max/M
    total_data_size = data_size*max/M
    total_size = total_doc_size + total_data_size
    sizes = [doc_size, data_size, total_doc_size, total_data_size, total_size]
    print "\t".join(map(str, [label] + sizes))

def main():
    get_sizes("works", "/works/OL%dW", works, N)
    get_sizes("books", "/books/OL%dM", editions, N)
    get_sizes("authors", "/authors/OL%dA", authors, N)

if __name__ == "__main__":
    main()
