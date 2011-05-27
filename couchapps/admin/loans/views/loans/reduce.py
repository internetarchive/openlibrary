def _reduce(keys, values, rereduce):
    from collections import defaultdict
    d = defaultdict(lambda: 0)
    
    for v in values:
        for k, count in v.items():
            d[k] = d[k] + count
    
    return d