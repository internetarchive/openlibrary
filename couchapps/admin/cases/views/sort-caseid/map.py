def map(doc):
    if doc.get("type","") == "case":
        yield [doc.get('_id'), 
               doc.get('history',[{}])[-1].get("at","")
               ], 1
