def map(doc):
    if doc.get("type","") == "case":
        yield [doc.get('assignee'), 
               doc.get('history',[{}])[-1].get("at","")
               ], 1
