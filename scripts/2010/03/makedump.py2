"""Parse data table dump and generate tsv with "key", "type", "revision", "json" columns.
"""
import _init_path
import sys
from openlibrary.data import parse_data_table

def main(filename):
    for cols in parse_data_table(filename):
        print "\t".join(cols)

if __name__ == "__main__":
    main(sys.argv[1])
