import sys
from MARC21 import *
from MARC21Biblio import *
from catalog.lang import *

def isbn_parser (file):
    f = MARC21BiblioFile (file)
    try:
        while True:
            try:
                item = f.next_record()
		isbn = item['isbn_10']
		if isbn:
			yield isbn
            except MARC21Exn, e:
                warn ("couldn't interpret item: %s" % e)
    except StopIteration:
        pass

for isbn in isbn_parser (sys.stdin):
	print isbn
