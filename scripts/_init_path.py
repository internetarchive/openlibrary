"""Helper to add openlibrary module to sys.path.
"""

from os.path import abspath, join, dirname, pardir
import sys

OL_PATH = abspath(join(dirname(__file__), pardir))
sys.path.insert(0, OL_PATH)
