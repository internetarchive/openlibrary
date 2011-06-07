def map(doc):
     if doc.get("type","") == "case":
          yield doc["_id"], doc
