def _map(doc):
    lib = doc.get("library")
    status = doc.get("status")
    if lib:
        yield [lib, status], 1
