import sys, os

def find_sources():
    for p in sys.path:
        f = p + "/catalog/marc/sources"
        if os.path.exists(f):
            return f

def sources():
    return [tuple(i[:-1].split('\t')) for i in open(find_sources())]
