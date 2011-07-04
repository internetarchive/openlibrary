def map(doc):
    if doc.get("type","") == "case":
        yield [doc.get("status"),
               doc.get('creator_name'), 
               doc.get('history',[{}])[-1].get("at","")
               ], 1
