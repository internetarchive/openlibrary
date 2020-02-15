"""Infobase extension for Open Library.
"""

from openlibrary.olbase import events
from openlibrary.plugins import ol_infobase

def init_plugin():
    ol_infobase.init_plugin()
    events.setup()
