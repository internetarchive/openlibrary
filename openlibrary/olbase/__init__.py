"""Infobase extension for Open Library."""
from __future__ import annotations


from ..plugins import ol_infobase
from . import events


def init_plugin():
    ol_infobase.init_plugin()
    events.setup()
