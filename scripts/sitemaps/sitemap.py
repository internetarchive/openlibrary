"""Script to generate XML sitemap of openlibrary.org website.
"""

import web
import os
import itertools
import datetime

t_sitemap = """$def with (things)
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    $for t in things:
	<url>
	    <loc>http://openlibrary.org$t.key</loc>
	    <lastmod>$t.last_modified</lastmod>
	</url>
</urlset>
"""

t_siteindex = """$def with (names, timestamp)
<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    $for x in names:
	<sitemap>
	    <loc>http://openlibrary.org/static/sitemaps/sitemap_${x}.xml.gz</loc>
	    <lastmod>$timestamp</lastmod>
	</sitemap>
</sitemapindex>
"""

sitemap = web.template.Template(t_sitemap)
siteindex = web.template.Template(t_siteindex)

def read(filename):
    headers = ["id", "key", "type", "last_modified"]
    for line in open(filename).xreadlines():
        tokens = line.strip().split("\t")
        t = web.storage(zip(headers, tokens))
	t.last_modified = t.last_modified.replace(' ', 'T') + 'Z'
	yield t
        
def group(things, n=50000):
    def f(t):
	return int(t.id)/n
    for _, x in itertools.groupby(things, f):
        yield x

def write(path, text):
    from gzip import open as gzopen
    print 'writing', path, text.count('\n')
    f = gzopen(path, 'w')
    f.write(text)
    f.close()
    os.system("gzip " + path)

def make_siteindex(filename):
    groups = group(read(filename))
    
    if not os.path.exists('sitemaps'):
        os.mkdir('sitemaps')
    
    for i, x in enumerate(groups):
        write("sitemaps/sitemap_%04d.xml.gz" % i, sitemap(x))
    names = ["%04d" % j for j in range(i)]
    timestamp = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
    index = siteindex(names, timestamp)
    write("sitemaps/siteindex.xml.gz", index)
        
if __name__ == "__main__":
    import sys
    make_siteindex(sys.argv[1])

