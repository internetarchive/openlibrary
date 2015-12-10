"""Infobase extension for Open Library.
"""

from . import events
from ..plugins import ol_infobase

def init_plugin():
    ol_infobase.init_plugin()
    events.setup()
