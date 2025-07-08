"""Infobase extension for Open Library."""

from ..plugins import ol_infobase
from . import events


def init_plugin() -> None:
    ol_infobase.init_plugin()
    events.setup()
