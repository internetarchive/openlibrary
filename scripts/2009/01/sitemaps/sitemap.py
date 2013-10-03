"""Script to generate XML sitemap of openlibrary.org website.

USAGE:
    
    python sitemaps.py suffix dump.txt.gz
"""

import web
import os
import itertools
import datetime
import gzip
import json
import re
from openlibrary.core import helpers as h

t_sitemap = """$def with (things)
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    $for t in things:
    <url>
        <loc>http://openlibrary.org$t.path</loc>
        <lastmod>$t.last_modified</lastmod>
    </url>
</urlset>
"""

t_siteindex = """$def with (names, timestamp)
<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    $for name in names:
    <sitemap>
        <loc>http://openlibrary.org/static/sitemaps/$name</loc>
        <lastmod>$timestamp</lastmod>
    </sitemap>
</sitemapindex>
"""

sitemap = web.template.Template(t_sitemap)
siteindex = web.template.Template(t_siteindex)

def xopen(filename):
    if filename.endswith(".gz"):
        return gzip.open(filename)
    else:
        return open(filename)

def process_dump(dumpfile):
    """Generates a summary file used to generate sitemaps.

    The summary file contains: sort-key, path and last_modified columns.
    """
    rows = (line.strip().split("\t") for line in xopen(dumpfile))
    for type, key, revision, last_modified, jsontext in rows:
        if type not in ['/type/edition', '/type/work', '/type/author']:
            continue

        """
        doc = json.loads(jsontext)
        if type == '/type/author':
            title = doc.get('name', 'unnamed')
        else:
            title = doc.get('title', 'untitled')
        
        path = key + "/" + h.urlsafe(title.strip())
        """
        path = key
        last_modified = last_modified.replace(' ', 'T') + 'Z'
        sortkey = get_sort_key(key)
        if sortkey:
            print "\t".join([sortkey, path.encode('utf-8'), last_modified])

re_key = re.compile("^/(authors|books|works)/OL\d+[AMW]$")

def get_sort_key(key):
    """Returns a sort key used to group urls in 10K batches.

    >>> get_sort_key("/books/OL12345678M")
    'books_1234'
    >>> get_sort_key("/authors/OL123456A")
    'authors_0012'
    """
    m = re_key.match(key)
    if not m:
        return
    prefix = m.group(1)
    num = int(web.numify(key)) / 10000
    return "%s_%04d" % (prefix, num)

def generate_sitemaps():
    os.system("rm -rf sitemaps; mkdir sitemaps")
    rows = (line.strip().split("\t") for line in sys.stdin)
    for sortkey, chunk in itertools.groupby(rows, lambda row: row[0]):
        things = [web.storage(path=path, last_modified=last_modified) for sortkey, path, last_modified in chunk]
        if things:
            write("sitemaps/sitemap_%s.xml.gz" % sortkey, sitemap(things))

def generate_siteindex():
    filenames = sorted(os.listdir("sitemaps"))
    if "siteindex.xml.gz" in filenames:
        filenames.remove("siteindex.xml.gz")
    timestamp = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
    index = siteindex(filenames, timestamp)
    write("sitemaps/siteindex.xml.gz", index)

def write(path, text):
    text = web.safestr(text)
    print 'writing', path, text.count('\n')
    f = gzip.open(path, 'w')
    f.write(text)
    f.close()
    #os.system("gzip " + path)

def main(dumpfile):
    cmd = "python %s '%s' --process | sort -S 1G | python %s --generate" % (sys.argv[0], dumpfile, sys.argv[0])
    print cmd
    os.system(cmd)

if __name__ == "__main__":
    import sys
    if "--process" in sys.argv:
        sys.argv.remove("--process")
        process_dump(sys.argv[1])
    elif "--generate" in sys.argv:
        sys.argv.remove("--generate")
        generate_sitemaps()
    elif "--siteindex" in sys.argv:
        generate_siteindex()

