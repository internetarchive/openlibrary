"""
Generate scod report.
"""
import simplejson
import os

def parse():
    for f in os.listdir('data/scan_record/b'):
        path = 'data/scan_record/b/' + f
        d = simplejson.loads(open(path).read())
        status = d['scan_status']
        if status in ['WAITING_FOR_BOOK', 'SCAN_IN_PROGRESS', 'BOOK_NOT_SCANNED', 'SCAN_COMPLETE']:
            if d.get('request_date'):
                yield 'request', d['request_date'], d

        if status == 'SCAN_COMPLETE':
            if 'completion_date' in d:
                yield 'complete', d['completion_date'], d

        if status == 'BOOK_NOT_SCANNED':
            yield 'notfound', d['last_modified']['value'], d

def main():
    data = {}
    for action, date, d in parse():
        date = date[:10] # keep only YYYY-MM-DD
        data.setdefault(date, dict(request=[], complete=[], notfound=[]))[action].append(d)

    for k in sorted(data.keys()):
        d = data[k]
        reasons = [r['comment'] for r in d['notfound']]
        print "%s\t%s\t%s\t%s\t%s" % (k, len(d['request']), len(d['complete']), len(d['notfound']), reasons)

if __name__ == "__main__":
    main()
