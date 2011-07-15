def map(doc):
    if doc.get("type","") == "case":
        yield [int(doc.get('_id').replace("case-","")),
               doc.get('history',[{}])[-1].get("at","")
               ], 1
