"""Helper to add openlibrary module to sys.path.
"""

import os
from os.path import abspath, realpath, join, dirname, pardir
import sys

path = __file__.replace('.pyc', '.py') 
scripts_root = dirname(realpath(path))

OL_PATH = abspath(join(scripts_root, pardir))
sys.path.insert(0, OL_PATH)

# Add the PWD as the first entry in the path.
# The path we get from __file__ and abspath will have all the links expanded.
# This creates trouble in symlink based deployments. Work-around is to add the
# current directory to path and let the app run from that directory.
sys.path.insert(0, os.getcwd())
