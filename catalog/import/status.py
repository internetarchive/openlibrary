import web, cjson
import urllib2
from pprint import pformat
from time import time

urls = (
    '/', 'index'
)

base_url = "http://0.0.0.0:9020/"

done = set(['marc_western_washington_univ', 'marc_miami_univ_ohio'])

files = eval(open('files').read())

def server_read(path):
    return cjson.decode(urllib2.urlopen(base_url + path).read())

def progress(archive, part, pos):
    total = 0
    pass_cur = False
    for f, size in files[archive]:
        cur = archive + '/' + f
        if size is None:
            return (None, None)
        size = int(size)
        if cur == part or part == f:
            pass_cur = True
        if not pass_cur:
            pos += size
        total += size
    assert pass_cur
    return (pos, total)

class index:
    def GET(self): # yes, this is a bit of a mess
        web.header('Content-Type','text/html; charset=utf-8', unique=True)
        web.header('Refresh','60', unique=True)
        print "<html>\n<head><title>Import status</title>"
        print "<style>th { vertical-align: bottom; text-align: left }</style>"
        print "</head><body>"
        print "<h1>Import status</h1>"
        print "<table>"
        print "<tr><th>Archive ID</th><th>import</th><th>loaded</th><th>input<br>(rec/sec)</th>"
        print "<th>no match<br>(%)</th>"
        print "<th>load<br>(rec/sec)</th>"
        print "<th>last update<br>(secs)</th><th>running<br>(hours)</th>"
        print "<th>progress</th>"
        print "<th>remaining<br>(hours)</th>"
        print "</tr>"
        cur_time = time()
        total_recs = 0
        total_t = 0
        total_load = 0
        total_rec_per_sec = 0
        total_load_per_sec = 0
        for k in server_read('keys'):
            if k.endswith('2'):
                continue

            broken = False
            q = server_read('store/' + k)
            t1 = cur_time - q['time']
            rec_no = q['rec_no']
            chunk = q['chunk']
            load_count = q['load_count']
            rec_per_sec = rec_no / q['t1']
            load_per_sec = load_count / q['t1']
            if k in done:
                print '<tr bgcolor="#00ff00">'
                broken = True
            elif t1 > 120:
                broken = True
                print '<tr bgcolor="red">'
            else:
                print '<tr>'
                total_rec_per_sec += rec_per_sec
                total_load_per_sec += load_per_sec
                total_recs += rec_no
                total_load += load_count
                total_t += q['t1']
            print '<td><a href="http://archive.org/details/%s">%s</a></td>' % (k.rstrip('2'), k)
            print '<td><a href="http://openlibrary.org/show-marc/%s">current record</a></td>' % q['cur']
            if 'last_key' in q and q['last_key']:
                last_key = q['last_key']
                print '<td><a href="http://openlibrary.org%s">%s</a></td>' % (last_key, last_key[3:])
            else:
                print '<td>No key</td>'
            if k in done:
                for i in range(5):
                    print '<td></td>'
                print '<td align="right">100.0%</td>'
            else:
                print '<td align="right">%.2f</td>' % rec_per_sec
                print '<td align="right">%.2f%%</td>' % (float(q['load_count'] * 100.0) / q['rec_no'])
                print '<td align="right">%.2f</td>' % load_per_sec
                print '<td align="right">%.2f</td>' % t1
                hours = q['t1'] / 3600.0
                print '<td align="right">%.2f</td>' % hours
                (pos, total) = progress(k, q['part'], q['pos'])
                if pos:
                    print '<td align="right">%.2f%%</td>' % (float(pos * 100) / total)
                else:
                    print '<td align="right">n/a</td>'
                if 'bytes_per_sec_total' in q and total is not None and pos:
                    remaining_bytes = total - pos
                    sec = remaining_bytes / q['bytes_per_sec_total']
                    hours = sec / 3600
                    print '<td align="right">%.2f</td>' % hours
                else:
                    print '<td></td>'

            print '</tr>'
        print '<tr><td>Total</td><td></td><td></td><td align="right">%.2f</td>' % total_rec_per_sec
        if total_recs:
            print '<td align="right">%.2f%%</td>' % (float(total_load * 100.0) / total_recs)
        else:
            print '<td align="right"></td>' 
        print '<td align="right">%.2f</td>' % total_load_per_sec
        print '</tr></table>'
        print "<table>"
        print '<tr><td align="right">loading:</td><td align="right">%.1f</td><td>rec/day</td></tr>' % (total_load_per_sec * (60 * 60 * 24))
        if total_load_per_sec:
            print '<tr><td>one million records takes:</td><td align="right">%.1f</td><td>days</td></tr>' % ((1000000 / total_load_per_sec) / (60 * 60 * 24))
        print "</table>"
        print '</body>\n<html>'

web.webapi.internalerror = web.debugerror

if __name__ == '__main__':
    web.run(urls, globals(), web.reloader)
