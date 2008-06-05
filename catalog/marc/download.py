#!/usr/bin/python
# downloader so Karen doesn't need to download entire MARC files
import web
import web.form as form
import urllib2
from pprint import pprint

urls = (
    '/', 'index',
    '/(bpl\d+\.mrc):(\d+):(\d+)', 'get',
)

files = (
    ('bpl101.mrc', 50000),
    ('bpl102.mrc', 50000),
    ('bpl103.mrc', 50000),
    ('bpl104.mrc', 50000),
    ('bpl105.mrc', 50000),
    ('bpl106.mrc', 50000),
    ('bpl107.mrc', 50000),
    ('bpl108.mrc', 50000),
    ('bpl109.mrc', 50000),
    ('bpl110.mrc', 50000),
    ('bpl111.mrc', 50000),
    ('bpl112.mrc', 50000),
    ('bpl113.mrc', 50000),
    ('bpl114.mrc', 50000),
    ('bpl115.mrc', 50000),
    ('bpl116.mrc', 50000),
    ('bpl117.mrc', 50000),
    ('bpl118.mrc', 49997),
    ('bpl119.mrc', 50000),
    ('bpl120.mrc', 50000),
    ('bpl121.mrc', 50000),
    ('bpl122.mrc', 49999),
    ('bpl123.mrc', 50000),
    ('bpl124.mrc', 50000),
    ('bpl125.mrc', 50000),
    ('bpl126.mrc', 50000),
    ('bpl127.mrc', 50000),
    ('bpl128.mrc', 49999),
    ('bpl129.mrc', 49999),
    ('bpl130.mrc', 50000),
    ('bpl131.mrc', 49999),
    ('bpl132.mrc', 50000),
    ('bpl133.mrc', 50000),
    ('bpl134.mrc', 49999),
    ('bpl135.mrc', 50000),
    ('bpl136.mrc', 50000),
    ('bpl137.mrc', 49999),
    ('bpl138.mrc', 50000),
    ('bpl139.mrc', 50000),
    ('bpl140.mrc', 50000),
    ('bpl141.mrc', 50000),
    ('bpl142.mrc', 50000),
    ('bpl143.mrc', 50000),
    ('bpl144.mrc', 50000),
    ('bpl145.mrc', 50000),
    ('bpl146.mrc', 50000),
    ('bpl147.mrc', 41036),
)

myform = form.Form( 
    form.Dropdown('file', [(i, "%s - %d records" % (i, j)) for i, j in files]),
    form.Textbox("start", 
        form.notnull,
        form.regexp('\d+', 'Must be a digit'),
        form.Validator('Must be less than 50000', lambda x:int(x)>50000)),
    form.Textbox("count", 
        form.notnull,
        form.regexp('\d+', 'Must be a digit'),
        form.Validator('Must be less than 50000', lambda x:int(x)>50000)))

def start_and_len(file, start, count):
    f = urllib2.urlopen("http://archive.org/download/bpl_marc/" + file)
    pos = 0
    num = 0
    start_pos = None
    while num < start + count:
        data = f.read(5)
        if data == '':
            break
        rec_len = int(data)
        f.read(rec_len-5)
        pos+=rec_len
        num+=1
        if num == start:
            start_pos = pos

    f.close()
    return (start_pos, pos - start_pos)

class index:
    def GET(self):
        this_form = myform()
        this_form.fill()
        print '<form name="main" method="get">'
        if not this_form.valid:
            print '<p class="error">Try again:</p>'
        print this_form.render()
        print '<input type="submit"></form>'
        if this_form['start'].value:
            file = this_form['file'].value
            (offset, length) = start_and_len(file, int(this_form['start'].value), int(this_form['count'].value))
            print "%.1fKB" % (float(length) / 1024.0)
            url = "http://wiki-beta.us.archive.org:9090/%s:%d:%d" % (file, offset, length)
            print '<a href="%s">download</a>' % url

class get:
    def GET(self, file, offset, length):
        offset = int(offset)
        length = int(length)
        web.header("Content-Type","application/octet-stream")
        r0, r1 = offset, offset+length-1
        url = "http://archive.org/download/bpl_marc/" + file
        ureq = urllib2.Request(url, None, {'Range':'bytes=%d-%d'% (r0, r1)},)
        f = urllib2.urlopen(ureq)
        while 1:
            buf = f.read(1024)
            if not buf:
                break
            web.output(buf)
        f.close()

web.webapi.internalerror = web.debugerror

if __name__ == "__main__": web.run(urls, globals(), web.reloader)
