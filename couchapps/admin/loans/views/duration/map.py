def _map(doc):
    import re, datetime
    def parse_datetime(datestring):
        """Parses from isoformat.
        Is there any way to do this in stdlib?
        """
        tokens = re.split('-|T|:|\.| ', datestring)
        return datetime.datetime(*map(int, tokens))
        
    if doc.get('status') == 'completed':
        t_start = parse_datetime(doc['t_start'])
        t_end = parse_datetime(doc['t_end'])
        delta = t_end - t_start
        duration = delta.days * 24 * 60 + delta.seconds / 60 # duration in minutes
        
        yield [t_end.year, t_end.month, t_end.day], duration