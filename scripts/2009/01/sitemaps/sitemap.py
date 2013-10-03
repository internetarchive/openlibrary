"""Script to generate XML sitemap of openlibrary.org website.

USAGE:
    
    python sitemaps.py suffix dump.txt.gz
"""

import web
import os
import itertools
import datetime
import gzip
#import json
import re
import time

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
            yield [sortkey, path.encode('utf-8'), last_modified]

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

def generate_sitemaps(filename):
    rows = (line.strip().split("\t") for line in open(filename))
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
    log('writing', path, text.count('\n'))
    f = gzip.open(path, 'w')
    f.write(text)
    f.close()
    #os.system("gzip " + path)

def write_tsv(path, rows):
    lines = ("\t".join(row) + "\n" for row in rows)
    f = open(path, "w")
    f.writelines(lines)
    f.close()

def system_memory():
    """Returns system memory in MB."""
    try:
        x = os.popen("cat /proc/meminfo | grep MemTotal | sed 's/[^0-9]//g'").read()
        # proc gives memory in KB, converting it to MB
        return int(x)/1024
    except IOError:
        # default to 1024MB
        return 1024

def system(cmd):
    log("executing:", cmd)
    status = os.system(cmd)
    if status != 0:
        raise Exception("%r failed with exit status: %d" % (cmd, status))

def log(*args):
    msg = " ".join(map(str, args))
    print time.asctime(), msg

def main(dumpfile):
    system("rm -rf sitemaps sitemaps_data.txt*; mkdir sitemaps")

    log("processing the dump")
    rows = process_dump(dumpfile)
    write_tsv("sitemaps_data.txt", rows)

    log("sorting sitemaps_data.txt")
    # use half of system of 3GB whichever is smaller
    sort_mem = min(system_memory()/2, 3072)
    system("sort -S%dM sitemaps_data.txt > sitemaps_data.txt.sorted" % sort_mem)

    log("generating sitemaps")
    generate_sitemaps("sitemaps_data.txt.sorted") 
    generate_siteindex()

    log("done")

if __name__ == "__main__":
    import sys
    main(sys.argv[1])
