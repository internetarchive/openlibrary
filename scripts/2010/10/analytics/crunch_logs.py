#!/usr/bin/env python

import gzip, re, urlparse, collections, datetime, httplib, csv, os, sys
import lxml.etree

from optparse import OptionParser


LOG_FORMAT = re.compile(r'^(?P<ip>[0-9.]+) (?P<host>[\S]+) (?P<dunno>[\S]+)\ '
                        '\[(?P<date>[^\]]+)\] "(?P<req>.*)" (?P<code>\d{3}) (?P<size>(\d+|-))\ '
                        '"(?P<referrer>.+)"\ "(?P<user_agent>.+)"\ (?P<offset>\d+)$')



def load_user_agent_map():
    conn = httplib.HTTPConnection("www.user-agents.org")
    try:
        conn.putrequest("GET", "/allagents.xml")
        conn.putheader("User-Agent", "OpenlibraryAnalyticsBot/1.0 (http://www.openlibrary.org)")
        conn.endheaders()
        resp = conn.getresponse()
        assert int(resp.status) == 200
        data = lxml.etree.fromstring(resp.read())
    finally:
        conn.close()
    result = {}
    for ua in data.iterchildren():
        t = ua.find("Type").text
        t = tuple(t.split()) if t else tuple()
        result[ua.find("String").text] = t
    return result

class UserAgent:
    """
    Counts user agent categorization as described by www.user-agents.org.
    Useful for distinguishing browser/bot requests.
    """

    name = "ua_type"
    
    def __init__(self):
        self._user_agent_map = load_user_agent_map()

    def map(self, line):
        # determine if the request is being made by a browser
        if line['user_agent'] not in user_agent_map:
            if ('bot' in line['user_agent'] 
                or 'http://' in line['user_agent']
                or line['user_agent'].startswith("Python-urllib")):
                # just make it a bot
                user_agent_map[line['user_agent']] = ('R',)
            else:
                user_agent_map[line['user_agent']] = ('B',)
                
        line['is_bot'] = 'B' not in user_agent_map.get(line['user_agent'])

        return dict((ua_type, 1) for ua_type in user_agent_map.get(line['user_agent'], []))

class ResponseCode:
    """
    Maps a line to its status code.
    """

    name = "response_code"

    def map(self, line):
        return {line['code']: 1}

class RequestType:
    """
    Fuzzy breakdown of request by its type (api, web, media, etc)
    """

    name = "request_type"

    def map(self, line):
        req_type = 'other'
        if line['req']:
            req = line['req'].split()
            if len(req) == 3:
                req = urlparse.urlsplit(req[1]).path
                if req.startswith(("/api", "/query.json")) or req.endswith(".json"):
                    req_type = 'api'
                elif req.startswith(("/css", "/images")):
                    req_type = 'media'
                else:
                    req_type = 'web'

        line['request_type'] = req_type
        return {req_type: 1}

class Referrer:
    """
    Maps to referrer for non bot requests.
    """

    name = "referrer"

    def map(self, line):
        if not line['referrer'] or line.get('is_bot', True) or line.get('request_type') != 'web':
            return None
        line['referrer'] = urlparse.urlsplit(line['referrer']).netloc
        if line['referrer'] in ('localhost', 'openlibrary.org'):
            line['referrer'] = None
        if line['referrer']:
            return {line['referrer']: 1}

class PageType:
    """
    Fuzzy page type breakdown (book, author, work, etc)
    """

    name = "page_type"
    
    def map(self, line):
        if line['code'] != 200:
            return
        if not line['req']:
            return {"unknown": 1}
        req = line['req'].split()
        if len(req) != 3:
            return {"unusual": 1}
        req = urlparse.urlsplit(req[1]).path
        if not req or req[0] != "/":
            print "%s: malformed %s" % (self.name, line['req'])
            return {"malformed": 1}
        if req.startswith(("/api/", "/query")):
            return {'api': 1}
        elif req.startswith(("/css/", "/images/", "/js/", "/static/", "/favicon.ico")):
            return None #{"images/js/css": 1}
        elif req.startswith(("/w/", "/works")):
            return {'work': 1}
        elif req.startswith(("/b/", "/books")):
            return {'books': 1}
        elif req.startswith(("/a/", "/authors")):
            return {'author': 1}
        elif req == "/":
            return {'home': 1}

        result = req.split("/")[1]
        if result.endswith(".json"):
            result = result[:-len(".json")]
        return {result: 1}

class ApiRequestType:
    """
    Fuzzy breakdown of api request type (work, author, book, query, etc)
    """

    name = "api_request_type"

    def map(self, line):
        req_type = 'other'
        if not line['req']:
            return
        req = line['req'].split()
        if len(req) != 3:
            return
        req = urlparse.urlsplit(req[1]).path
        if req.startswith("/query"):
            return {"query": 1}
        if req.endswith(".json"):
            req = req[:-len(".json")]
            return {"%s.json" % {
                    "w": "works", "works": "works",
                    "b": "books", "books": "books",
                    "a": "authors", "authors": "authors"
                    }.get(req.split("/")[1], req.split("/")[1]): 1}
        if req.startswith("/api"):
            req = req.split("/")
            if len(req) < 3:
                return {"unknown.api": 1}
            else:
                return {"%s.api" % req[2]: 1} 
            
        return None

def main():
    """
    Takes a stream of access logs and processes them with each of the processors.
    Example usage:
    # (find . -name 'access.log.gz' -exec zcat {} \; ; find . -name 'access.log' -exec cat {} \; ;) | crunch_logs.py -d /tmp/crunched
    """
    parser = OptionParser(usage="%prog -d [dest]")
    parser.add_option("-d", "--dest", dest="dest",
                      default="/tmp",
                      help="Where to emit tsvs")

    options, args = parser.parse_args()
    user_agent_map = load_user_agent_map()

    if len(args) == 1:
        fn = args[0]
        f = gzip.open(fn) if fn.endswith(".gz") else open(fn)
    else:
        f = sys.stdin

    # collection, thing, date, value
    data = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.defaultdict(int)))

    processors = (
        ResponseCode(), RequestType(), UserAgent(), 
        Referrer(), PageType(), ApiRequestType()
    )

    for line in f:
        if not line:
            break
        try:
            line = LOG_FORMAT.match(line.strip()).groupdict()
        except Exception, e:
            print "FAIL: %s" % line
            continue
        if line['referrer'] == '-':
            line['referrer'] = None
        if line['dunno'] == '-':
            line['dunno'] = None

        if line['host'] != 'openlibrary.org':
            continue

        # some minor normalization of the line
        line.update({'code': int(line['code']), 
                     'size': None if line['size'] == '-' else int(line['size']), 
                     'offset': int(line['offset']),
                     'date': datetime.datetime.strptime(line['date'][:len("dd/mm/yyyy") + 1], "%d/%b/%Y").date()})

        for p in processors:
            # for each processor map to some data
            m = p.map(line)
            if not m:
                continue
            for value, count in m.iteritems():
                # the reduce step is implicitly a sum operation right now
                data[p.name][line['date']][value] += count

#    for d, stats in referrers.itermitems():
#        hosts_sorted = sorted(stats.keys(), key=lambda host: stats[host])
#        top_n = dict((host, stats[host]) for hosts_sorted[:100])
    for table_name, table in data.iteritems():
        # do some totals so we can filter down to top100 since more data than that is unmanagable
        # in a csv
        totals = collections.defaultdict(int)
        for day in table.itervalues():
            for value, count in day.iteritems():
                totals[value] += count

        data[table_name]['totals'] = totals

        # filter down to top 100 for each day
        top_100 = sorted(totals.keys(), key=lambda k: totals[k], reverse=True)[:100]
        for date in table.keys():
            table[date] = dict((k, table[date][k]) for k in table[date].iterkeys() if k in top_100)

    for table_name, table in data.iteritems():
        f = open(os.path.join(options.dest, "%s.csv" % table_name), 'w')
        out = csv.writer(f, delimiter='\t')
        for date, day in table.iteritems():
            for value, count in day.iteritems():
                out.writerow([date.isoformat() if isinstance(date, datetime.date) else date, value, count])
        f.close()

if __name__ == "__main__":
    main()

# helpfull shell stuff for debugging

#print('\n'.join(['\t'.join([("%s)" % (i + 1)).ljust(4), h.ljust(40), str(y[h])]) for i, h in enumerate(sh)]))
#grep 2010-09-21 referrers.csv | awk '{printf "%d\t%s\n", $3, $2}' | sort -nr
#(find tmp/logs/ -name '*.gz' -exec bash -c 'gzip -dc {} | head -n 10000'  \; ;) | python src/scratch/01.py -d tmp/y/
# for i in `find . -name *.gz`; do j=`echo $i | sed -e "s/\.\/\([0-9]*\)\/\([0-9]*\)\(.*\)/access_\1_\2.log.gz/g"`; echo $j; scp $i ariel@ia331503:/0/logs/$j; done
# (find . -name 'access.log.gz' -exec zcat {} \; ; find . -name 'access.log' -exec cat {} \; ;)
