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

import web
from gzip import open as gzopen

from openlibrary.plugins.openlibrary.processors import urlsafe

t = web.Template

t_sitemap = t("""$def with (docs)
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    $for doc in docs:
        <url>
            <loc>http://openlibrary.org$doc.path</loc>
            <lastmod>$doc.last_modified</lastmod>
        </url>
</urlset>
""")

t_siteindex = t("""$def with (names, timestamp)
<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    $for x in names:
        <sitemap>
            <loc>http://openlibrary.org/static/sitemaps/sitemap_${x}.xml.gz</loc>
            <lastmod>$timestamp</lastmod>
        </sitemap>
</sitemapindex>
""")

def process_doc(doc):
    """Process the doc and initialize doc.path."""

def generate_sitemap(docs):
    for doc in docs:
        process_doc(doc)
    return web.safestr(t_sitemap(docs))

def find_path(key, type, json):
    if type in ['/type/edition', '/type/work']:
        data = simplejson.loads(json)
        return key + '/' + urlsafe(data.get('title', 'untitled'))
    elif doc.type == '/type/author':
        data = simplejson.loads(json)
        return key + '/' + urlsafe(data.get('name', 'unnamed'))
    else:
        return doc.key
    
def read_dump(dump_file):
    for line in open(dump_file):
        type, key, revision, timestamp, json = line.strip.split('\t')
        yield web.storage(type=type, key=key, path=find_path(json), timestamp=timestamp)

def gzwrite(path, data):
    f = gzopen(path, 'w')
    f.write(data)
    f.close()
    
def write_sitemaps(data, outdir, prefix):
    for i, rows in enumerate(web.group(data, 10000)):
        rows = list(rows)
        last_modifed = max(row[-1] for row in rows)
        
        filename = "sitemap_%s_%04d.xml.gz" % (prefix, i)
        print >> sys.stderr, "generating", filename
        
        path = os.path.join(outdir, filename)
        sitemap = web.safestr(t_sitemap(rows))
        
        gzwrite(path, sitemap)
        yield filename, last_modifed
        
def write_siteindex(data, outdir, prefix):
    rows = write_sitemaps(data, outdir, prefix)
    
    filename = "siteindex_%s.xml.gz" % prefix
    print >> sys.stderr, "generating", filename
    
    path = os.path.join(outdir, filename)
    siteindex = web.safestr(t_siteindex(rows))
    
    gzwrite(path, siteindex)

def generate_sitemaps(index_file, outdir, prefix):
    data = (line.strip().split("\t") for line in open(index_file))
    write_siteindex(data, outdir, prefix)

