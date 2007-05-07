from MARC21 import *
from MARC21Biblio import *
from lang import *

def parser (file):
    f = MARC21BiblioFile (file)
    try:
        while True:
            try:
                item = f.next()
                yield item
            except MARC21Exn, e:
                warn ("couldn't interpret item: %s" % e)
    except StopIteration:
        pass
