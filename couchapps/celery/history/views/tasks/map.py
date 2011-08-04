def map(doc):
    if doc["type"] == "task":
        yield [doc["command"], doc["finished_at"]], 1
        yield [None, doc['finished_at']], 1

