def map(doc):
    if doc.get("type","") == "case":
        yield [doc.get("status"),
               int(doc.get('_id').replace("case-","")),
               doc.get('history',[{}])[-1].get("at","")
               ], 1
