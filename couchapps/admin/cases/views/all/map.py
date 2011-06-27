def map(doc):
    if doc.get("type","") == "case":
        yield [doc.get('status'), doc.get('created')], 1
