"""How the other editions of a work fill a field. Live against the local database."""


def edition_field_values(edition, fld: str) -> list:
    raw = edition.get(fld)
    if raw in (None, "", []):
        return []
    if fld == "languages":
        return [lang.key.split("/")[-1] if hasattr(lang, "key") else str(lang).split("/")[-1] for lang in raw]
    if isinstance(raw, list):
        return list(raw)
    return [raw]
