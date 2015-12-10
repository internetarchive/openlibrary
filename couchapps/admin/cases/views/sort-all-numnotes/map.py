def map(doc):
    if doc.get("type","") == "case":
        yield [len(doc.get('history',[{}]))
               ], 1
