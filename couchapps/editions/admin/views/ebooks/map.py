def fun(doc):
    if "ocaid" in doc:
        yield doc["_id"], None 
