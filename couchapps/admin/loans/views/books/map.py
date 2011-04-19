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
      
    if 't_start' in doc and 'book'in doc:  
        t = parse_datetime(doc['t_start'])
        yield [doc['book'], t.year, t.month], 1