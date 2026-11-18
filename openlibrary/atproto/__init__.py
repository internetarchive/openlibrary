"""Read-only XRPC provider for the ``community.lexicon.media.book`` lexicons.

OpenLibrary answers the two published read-only procedures
(``resolveEditions`` and ``searchEditions``) by projecting its catalog into the
``defs#editionView`` shape. Nothing here writes repositories or records.
"""
