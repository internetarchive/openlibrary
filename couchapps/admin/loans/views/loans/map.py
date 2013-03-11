def _map(doc):
    if not doc['_id'].startswith("loans/"):
        return

    import re, datetime
    def parse_datetime(datestring):
        """Parses from isoformat.
        Is there any way to do this in stdlib?
        """
        tokens = re.split('-|T|:|\.| ', datestring)
        return datetime.datetime(*map(int, tokens))

    if 't_start' in doc:
        t = parse_datetime(doc['t_start'])        
        yield ["", t.year, t.month, t.day], {doc['resource_type']: 1, "total": 1}
        if "library" in doc:
            yield [doc["library"], t.year, t.month, t.day], {doc['resource_type']: 1, "total": 1}
