def _map(doc):
    import re, datetime
    def parse_datetime(datestring):
        """Parses from isoformat.
        Is there any way to do this in stdlib?
        """
        tokens = re.split('-|T|:|\.| ', datestring)
        return datetime.datetime(*map(int, tokens))

    if 't_start' in doc:
        t = parse_datetime(doc['t_start'])        
        yield [t.year, t.month, t.day], 1