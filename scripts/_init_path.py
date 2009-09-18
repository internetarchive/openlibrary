"""Helper to add openlibrary module to sys.path.
"""

from os.path import abspath, realpath, join, dirname, pardir
import sys

path = __file__.replace('.pyc', '.py') 
scripts_root = dirname(realpath(path))

OL_PATH = abspath(join(scripts_root, pardir))
sys.path.insert(0, OL_PATH)
