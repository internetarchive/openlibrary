def _map(doc):
    if not doc['_id'].startswith("/books/"):
        return

    counts = {}

    for k, count in doc['loans'].items():
        yyyy, mm = k.split("-")

        # store overall, per-year and per-month counts
        counts[""] = counts.get("", 0) + count
        counts[yyyy] = counts.get(yyyy, 0) + count
        counts[k] = counts.get(k, 0) + count

    for k, v in counts.items():
        yield [k, v], None
