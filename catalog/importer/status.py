import web, urllib2
import simplejson as json
from pprint import pformat
from time import time
from catalog.read_rc import read_rc

urls = (
    '/', 'index'
)

app = web.application(urls, globals())

base_url = "http://0.0.0.0:9020/"
rc = read_rc()

done = ['marc_western_washington_univ', 'marc_miami_univ_ohio', 'bcl_marc', 'marc_oregon_summit_records', 'CollingswoodLibraryMarcDump10-27-2008', 'hollis_marc', 'marc_laurentian', 'marc_ithaca_college', 'marc_cca']

def read_book_count():
    lines = list(open(rc['book_count']))
    t0, count0 = [int(i) for i in lines[0].split()]
    t, count = [int(i) for i in lines[-1].split()]
    t_delta = time() - t0
    count_delta = count - count0
    rec_per_sec = float(count_delta) / t_delta
    return rec_per_sec, count

files = eval(open('files').read())

def server_read(path):
    return json.load(urllib2.urlopen(base_url + path))

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
        page = ''
        page += "<html>\n<head><title>Import status</title>"
        page += "<style>th { vertical-align: bottom; text-align: left }</style>"
        page += "</head><body>"
        page += "<h1>Import status</h1>"
#        page += '<p style="padding: 5px; background: lightblue; border: black 1px solid; font-size:125%; font-weight: bold">MARC import is paused during the OCA conference</p>'
        page += "<b>Done:</b>"
        page += ', '.join('<a href="http://archive.org/details/%s">%s</a>' % (ia, ia) for ia in done) + '<br>'
        page += "<table>"
        page += "<tr><th>Archive ID</th><th>input<br>(rec/sec)</th>"
        page += "<th>no match<br>(%)</th>"
        page += "<th>load<br>(rec/sec)</th>"
#        page += "<th>last update<br>(secs)</th><th>running<br>(hours)</th>"
        page += "<th>progress</th>"
        page += "<th>remaining<br>(hours)</th>"
        page += "<th>remaining<br>(records)</th>"
        page += "</tr>"
        cur_time = time()
        total_recs = 0
        total_t = 0
        total_load = 0
        total_rec_per_sec = 0
        total_load_per_sec = 0
        total_future_load = 0
        for k in server_read('keys'):
            if k.endswith('2'):
                continue
            if k in done:
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
                page += '<tr bgcolor="#00ff00">'
                broken = True
            elif t1 > 600:
                broken = True
                page += '<tr bgcolor="red">'
            elif t1 > 120:
                broken = True
                page += '<tr bgcolor="yellow">'
            else:
                page += '<tr bgcolor="#00ff00">'
                total_rec_per_sec += rec_per_sec
                total_load_per_sec += load_per_sec
                total_recs += rec_no
                total_load += load_count
                total_t += q['t1']
            page += '<td><a href="http://archive.org/details/%s">%s</a></td>' % (k.rstrip('2'), k)
#            page += '<td><a href="http://openlibrary.org/show-marc/%s">current record</a></td>' % q['cur']
#            if 'last_key' in q and q['last_key']:
#                last_key = q['last_key']
#                page += '<td><a href="http://openlibrary.org%s">%s</a></td>' % (last_key, last_key[3:])
#            else:
#                page += '<td>No key</td>'
            if k in done:
                for i in range(5):
                    page += '<td></td>'
                page += '<td align="right">100.0%</td>'
            else:
                page += '<td align="right">%.2f</td>' % rec_per_sec
                no_match = float(q['load_count']) / q['rec_no']
                page += '<td align="right">%.2f%%</td>' % (no_match * 100)
                page += '<td align="right">%.2f</td>' % load_per_sec
                hours = q['t1'] / 3600.0
                page += '<td align="right">%.2f</td>' % hours
                (pos, total) = progress(k, q['part'], q['pos'])
                if pos:
                    page += '<td align="right">%.2f%%</td>' % (float(pos * 100) / total)
                else:
                    page += '<td align="right">n/a</td>'
                if 'bytes_per_sec_total' in q and total is not None and pos:
                    remaining_bytes = total - pos
                    sec = remaining_bytes / q['bytes_per_sec_total']
                    hours = sec / 3600
                    days = hours / 24
                    page += '<td align="right">%.2f</td>' % hours
                    total_bytes = q['bytes_per_sec_total'] * q['t1']
                    avg_bytes = total_bytes / q['rec_no']
                    future_load = ((remaining_bytes / avg_bytes) * no_match) 
                    total_future_load += future_load
                    page += '<td align="right">%s</td>' % web.commify(int(future_load))
                else:
                    page += '<td></td>'

            page += '</tr>'
        page += '<tr><td>Total</td><td align="right">%.2f</td>' % total_rec_per_sec
        if total_recs:
            page += '<td align="right">%.2f%%</td>' % (float(total_load * 100.0) / total_recs)
        else:
            page += '<td align="right"></td>' 
        page += '<td align="right">%.2f</td>' % total_load_per_sec
        page += '<td></td>' * 3 + '<td align="right">%s</td>' % web.commify(int(total_future_load))
        page += '</tr></table>'
#        page += "<table>"
#        page += '<tr><td align="right">loading:</td><td align="right">%.1f</td><td>rec/hour</td></tr>' % (total_load_per_sec * (60 * 60))
#        page += '<tr><td align="right">loading:</td><td align="right">%.1f</td><td>rec/day</td></tr>' % (total_load_per_sec * (60 * 60 * 24))
#        if total_load_per_sec:
#            page += '<tr><td>one million records takes:</td><td align="right">%.1f</td><td>hours</td></tr>' % ((1000000 / total_load_per_sec) / (60 * 60))
#            page += '<tr><td>one million records takes:</td><td align="right">%.1f</td><td>days</td></tr>' % ((1000000 / total_load_per_sec) / (60 * 60 * 24))
#        page += "</table>"
        rec_per_sec, count = read_book_count()
        page += "Total records per second: %.2f<br>" % rec_per_sec
        day = web.commify(int(rec_per_sec * (60 * 60 * 24)))
        page += "Total records per day: %s<br>" % day

        page += "Books in Open Library: " + web.commify(count) + "<br>"
        page += '</body>\n<html>'
        return page

if __name__ == '__main__':
    app.run()
