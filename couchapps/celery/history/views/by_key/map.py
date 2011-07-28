def map(doc):
    if doc.get("context",""):
        for i in doc.get("context",{}).get("keys",[]):
            yield i, doc
