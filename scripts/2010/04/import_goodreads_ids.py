#!/usr/bin/env python

from time import localtime, sleep, strftime
from olapi import OpenLibrary

ol = OpenLibrary()
ol.login("someBot", "somePassword")

def print_log(msg):
  timestamp = strftime("%Y%m%d_%H:%M:%S", localtime())
  print("[" + timestamp + "] " + msg)

def set_identifier(book, id_name, id_value):
  # OL handles the standard identifiers in a different way.
  if id_name in ["isbn_10", "isbn_13", "oclc_numbers", "lccn"]:
    ids = book.setdefault(id_name, [])
    if id_value not in ids:
      ids.append(id_value)
  else:
    ids = book.setdefault("identifiers", {})
    ids[id_name] = [id_value]

def set_goodreads_id(olid, goodreads_id):
  book = ol.get(olid)
  set_identifier(book, "goodreads", goodreads_id)
  ol.save(book['key'], book, "Added goodreads ID.")

def map_id(olid, isbn, goodreads_id):
  book = ol.get(olid)
  if book.has_key('identifiers'):
    if book['identifiers'].has_key('goodreads'):
      if goodreads_id in book['identifiers']['goodreads']:
        return
  print_log("Adding Goodreads ID \"" + goodreads_id + "\" to Openlibrary ID \"" + olid + "\"")
  set_goodreads_id(olid, goodreads_id)

def load(filename):
  n = 0
  for line in open(filename):
    olid, isbn, goodreads_id = line.strip().split()
    n = n+1
    if (n % 100000) == 0:
      print_log("(just read line " + str(n) + " from the map file)")
    is_good = False
    while (not is_good):
      try:
        map_id(olid, isbn, goodreads_id)
        is_good = True
      except:
        print_log("Exception for Goodreads ID \"" + goodreads_id + "\", message: \"" + str(sys.exc_info()[1]) + "\"")
        sleep(30)

if __name__ == "__main__":
  import sys
  load(sys.argv[1])

