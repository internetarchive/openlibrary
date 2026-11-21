from __future__ import annotations


class RecordError(Exception):
    """An edition cannot be projected onto an ``editionView``.

    Raised for catalog records that violate the lexicon's required fields (a
    missing title or creation timestamp). Callers skip such editions instead of
    failing the whole result page.
    """
