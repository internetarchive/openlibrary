def map(doc):
    if doc["type"] == "task":
        yield [doc["command"], doc["started_at"]], 1
        yield [None, doc['started_at']], 1

