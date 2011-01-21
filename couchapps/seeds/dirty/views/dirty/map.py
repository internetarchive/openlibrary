def map(doc):
    t = doc.get("dirty")
    if t:
        yield t, doc.get("works")
