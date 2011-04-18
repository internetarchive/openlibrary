def _reduce(keys, values, rereduce=False):
    if rereduce:
        sum = 0.0
        freq = {}
        count = 0
        for d in values:
            sum += d['avg'] * d['count']
            for k, v in d['freq'].items():
                freq[k] = freq.get(k, 0) + v
            count += d['count']
        return {"avg": sum/count, "freq": freq, "count": count}
    else:
        sum = 0.0
        freq = {}
        for value in values:
            sum += value
            freq[value/60] = freq.get(value/60, 0) + 1
        return {"avg": sum/len(values), "freq": freq, "count": len(values)}