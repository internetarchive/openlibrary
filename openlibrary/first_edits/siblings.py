"""How the other editions of a work fill a field, as spelling counts.

Live against the local database. The counts answer the normalization
question ("which spelling does this catalog already use?") and feed the
suggestions under the free-text answer.
"""

from collections import Counter
from dataclasses import dataclass

from openlibrary.first_edits.compare import norm_text, publisher_tokens


@dataclass(frozen=True)
class SiblingValue:
    display: str
    count: int


def _norm_key(fld: str, value) -> str:
    if fld == "publishers":
        return " ".join(sorted(publisher_tokens(str(value)))) or norm_text(str(value))
    if fld == "languages":
        return str(value)
    return norm_text(str(value))


def _edition_field_values(edition, fld: str) -> list:
    raw = edition.get(fld)
    if raw in (None, "", []):
        return []
    if fld == "languages":
        return [lang.key.split("/")[-1] if hasattr(lang, "key") else str(lang).split("/")[-1] for lang in raw]
    if isinstance(raw, list):
        return list(raw)
    return [raw]


def sibling_counts(editions, fld: str, exclude_key: str | None = None, limit: int = 8) -> list[SiblingValue]:
    """Distinct values across ``editions`` with counts, most common first.

    Values that normalize the same are merged and shown under their most
    common raw spelling.
    """
    groups: dict[str, Counter] = {}
    for ed in editions:
        if exclude_key and ed.key == exclude_key:
            continue
        for value in _edition_field_values(ed, fld):
            groups.setdefault(_norm_key(fld, value), Counter())[str(value)] += 1
    out = [SiblingValue(spellings.most_common(1)[0][0], sum(spellings.values())) for spellings in groups.values()]
    out.sort(key=lambda s: (-s.count, s.display))
    return out[:limit]


def sibling_counts_for_edition(edition, fld: str, limit: int = 8) -> tuple[list[SiblingValue], int]:
    """Counts across the edition's work siblings, plus how many siblings there are."""
    work = edition.works[0] if edition.works else None
    if not work:
        return [], 0
    editions = work.get_sorted_editions(keys=[edition.key])
    others = [e for e in editions if e.key != edition.key]
    return sibling_counts(others, fld, limit=limit), len(others)
