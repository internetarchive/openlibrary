def map(doc):
    if doc.get("type","") == "case":
        yield [doc.get("status"),
               len(doc.get('history',[{}]))
               ], 1
