def _map(doc):
    lib = doc.get("library")
    if lib:
        yield lib, 1
