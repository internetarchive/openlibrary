def fun(doc):
    if "covers" in doc:
        yield doc["_id"], None
