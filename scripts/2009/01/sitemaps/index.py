"""Script to generate HTML index of openlibrary.org website.
"""
import gzip
import os
import itertools
import web

def read_titles(filename):
    data = []
    for line in open(filename):
        id, title = line.strip().split('\t', 1)
        id = int(id)
        while len(data) <= id:
            data.extend(itertools.repeat(None, 1000000))
        data[id] = title
    return data

def read(titles_file, keys_file):
    titles = read_titles(titles_file)

    for line in open(keys_file):
        id, key, _ = line.split('\t', 2)
        id = int(id)
        title = titles[id] or key
        yield key, title

def take(n, seq):
    for i in xrange(n):
        yield seq.next()

def group(seq, n):
    while True:
        x = list(take(n, seq))
        if x: 
            yield x
        else:
            break

t_sitemap = """$def with (title, items)
<html>
<head><title>$title</title><head>
<body>

<h1>Books</h1>
<a href="../index.html">Back</a> | <a href="../../index.html">Back to index</a>
<ul>
$for key, title in seq:
    <li><a href="$key">$title</a></li>
</ul>
<a href="../index.html">Back</a> | <a href="../../index.html">Back to index</a>
</body>
</html>
"""

t_index = """$def with (title, files)
<html>
<head><title>$title</title><head>
<body>

<h1>$title</h1>

$if title != "index":
    <a href="../index.html">Back to index</a>

<ul>
$for key, title in seq:
    <li><a href="$key">$title</a></li>
</ul>

$if title != "index":
    <a href="../index.html">Back to index</a>
</body>
</html>
"""

make_sitemap = web.template.Template(t_sitemap)
make_index = web.template.Template(t_index)

def write(filename, text):
    f = open(filename, 'w')
    f.write(text)
    f.close()

def write_sitemap(i, seq):
    dir = 'index/%02d' % (i/1000)
    filename = "%s/index_%05d.html" % (dir, i)
    if not os.path.exists(dir):
        os.mkdir(dir)
    print filename
    write(filename, make_sitemap(filename, seq))

def write_sitemaps(data):
    for i, x in enumerate(group(data, 1000)):
        write_sitemap(i, x)

def main():
    import sys
    data = read(sys.argv[1], sys.argv[2])
    write_indexes(data)

    dirs = os.listdir('index'):
    write('index/index.html', make_index('index', dirs))

    for d in dirs:
        d = os.path.join('index', d)
        write(d + '/index.html', make_index('index', os.listdir(d))

if __name__ == "__main__":
    main()
