"""Library for generating sitemaps from Open Library dump.

Input for generating sitemaps is a tsv file with "path", "title", "created"
and "last_modified" columns. It is desirable that the file is sorted on 
"created" and "path".

http://www.archive.org/download/ol-sitemaps/sitemap-books-0001.xml.gz
http://www.archive.org/download/ol-sitemaps/sitemap-books-0001.xml.gz

http://www.archive.org/download/ol-sitemaps/sitindex-books.xml.gz
http://www.archive.org/download/ol-sitemaps/sitindex-authors.xml.gz
http://www.archive.org/download/ol-sitemaps/sitindex-works.xml.gz
http://www.archive.org/download/ol-sitemaps/sitindex-subjects.xml.gz
"""

import sys, os
import web
import datetime
from gzip import open as gzopen

from openlibrary.plugins.openlibrary.processors import urlsafe

t = web.template.Template

t_sitemap = t("""$def with (docs)
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
$for path, title, created, last_modified in docs:
    <url><loc>http://openlibrary.org$path</loc><lastmod>${last_modified}Z</lastmod></url>
</urlset>
""")

t_siteindex = t("""$def with (base_url, rows)
<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
$for filename, timestamp in rows:
    <sitemap><loc>$base_url/$filename</loc><lastmod>$timestamp</lastmod></sitemap>
</sitemapindex>
""")


t_html_layout = t("""$def with (page)
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
    "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
    <meta name="robots" content="noindex,follow" />
    <link href="/css/all.css" rel="stylesheet" type="text/css" />
    <title>$page.title</title>
</head>
<body id="edit">
<div id="background">
<div id="placement">
<div id="position">$:page</div>
</div>
</div>
</body></html>""")

t_html_sitemap = t("""$def with (back, docs)
$var title: Index
<p><a href="$back">&larr; Back to Index</a></p>
<ul>
$for path, title in docs:
    <li><a href="$path">$title</a></li>
</ul>
""")

def find_path(key, type, json):
    if type in ['/type/edition', '/type/work']:
        data = simplejson.loads(json)
        return key + '/' + urlsafe(data.get('title', 'untitled'))
    elif doc.type == '/type/author':
        data = simplejson.loads(json)
        return key + '/' + urlsafe(data.get('name', 'unnamed'))
    else:
        return doc.key

def gzwrite(path, data):
    f = gzopen(path, 'w')
    f.write(data)
    f.close()
    
def write_sitemaps(data, outdir, prefix):
    timestamp = datetime.datetime.utcnow().isoformat() + 'Z'
    
    # maximum permitted entries in one sitemap is 50K. 
    for i, rows in enumerate(web.group(data, 50000)):
        filename = "sitemap_%s_%04d.xml.gz" % (prefix, i)
        print >> sys.stderr, "generating", filename
        
        sitemap = web.safestr(t_sitemap(rows))
        
        path = os.path.join(outdir, filename)
        gzwrite(path, sitemap)
        yield filename, timestamp
        
def write_siteindex(data, outdir, prefix):
    rows = write_sitemaps(data, outdir, prefix)
    base_url = "http://openlibrary.org/static/sitemaps/"
    
    filename = "siteindex_%s.xml.gz" % prefix
    print >> sys.stderr, "generating", filename
    
    path = os.path.join(outdir, filename)
    siteindex = web.safestr(t_siteindex(base_url, rows))
    
    gzwrite(path, siteindex)
    
def parse_index_file(index_file):
    data = (line.strip().split("\t") for line in open(index_file))
    data = ([t[0], " ".join(t[1:-2]), t[-2], t[-1]] for t in data)    
    return data
    
def generate_sitemaps(index_file, outdir, prefix):
    data = parse_index_file(index_file)
    write_siteindex(data, outdir, prefix)
    
def mkdir_p(dir):
    if not os.path.exists(dir):
        os.makedirs(dir)
        
def write(path, data):
    print "writing", path
    mkdir_p(os.path.dirname(path))
    
    f = open(path, "w")
    f.write(data)
    f.close()
    
def dirindex(dir, back=".."):
    data = [(f, f) for f in sorted(os.listdir(dir))]
    index = t_html_layout(t_html_sitemap(back, data))
    
    path = dir + "/index.html"
    write(path, web.safestr(index))

def generate_html_index(index_file, outdir):
    data = parse_index_file(index_file)
    data = ((d[0], d[1]) for d in data)
    
    for i, chunk in enumerate(web.group(data, 1000)):
        back = ".."
        index = t_html_layout(t_html_sitemap(back, chunk))
        
        path = outdir + "/%02d/%05d.html" % (i/1000, i)
        write(path, web.safestr(index))

    for f in os.listdir(outdir):
        path = os.path.join(outdir, f)
        if os.path.isdir(path):
            dirindex(path)
    dirindex(outdir, back=".")
