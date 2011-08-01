def map(doc):
    if doc["type"] == "task":
        yield doc["_id"], 1 

