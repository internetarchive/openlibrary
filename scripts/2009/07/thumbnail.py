"""On disk datastructure for storing thumbnail images on disk.

Usage:

    $ python thumbnail.py f1.warc f2.warc f3.warc
"""
import sys, os
import Image
from cStringIO import StringIO
import time
import tarfile
import web

import warc

def makedirs(d):
    if not os.path.exists(d):
        os.makedirs(d)

def make_thumbnail(record):
    """Make small and medium thumbnails of given record."""
    id = record.get_header().subject_uri.split('/')[-1].split('.')[0]
    id = "%010d" % int(id)
    path = "/".join([id[0:3], id[3:6], id[6:9]])

    data = record.get_data()
    image = Image.open(StringIO(data))

    sizes = dict(S=(116, 58), M=(180, 360), L=(500, 500))

    yield id + "-O.jpg", data

    for size in "SML":
        imgpath = "%s-%s.jpg" % (id, size)
        try:
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            thumbnail = StringIO()
            image.resize(sizes[size], resample=Image.ANTIALIAS).save(thumbnail, format='jpeg')
            yield imgpath, thumbnail.getvalue()
        except Exception, e:
            print 'ERROR:', id, str(e)
            sys.stdout.flush()

def add_image(tar, name, data, mtime=None):
    tarinfo = tarfile.TarInfo(name)
    tarinfo.mtime = mtime or int(time.time())
    tarinfo.size = len(data)
    file = StringIO(data)
    tar.addfile(tarinfo, file)

def read(warc_files):
    for w in warc_files:
        print time.asctime(), w
        sys.stdout.flush()
        reader = warc.WARCReader(open(w))
        for r in reader.read():
            yield r

def process(warcfile, dir):
    outpath = dir + '/' + os.path.basename(warcfile).replace('.warc', '.tar')
    print 'process', warcfile, dir, outpath
    tar = tarfile.TarFile(outpath, 'w')

    def f(records):
        for r in records:
            timestamp = time.mktime(time.strptime(r.get_header().creation_date, '%Y%m%d%H%M%S'))
            try:
                for name, data in make_thumbnail(r):
                    yield name, data, timestamp
            except Exception, e:
                print >> sys.stderr, str(e)

    for name, data, timestamp in f(read([warcfile])):
        add_image(tar, name, data, mtime=timestamp)
    tar.close()

def main(dir, *warc_files):
    if not os.path.exists(dir):
        os.makedirs(dir)
    for w in warc_files:
        process(w, dir)

if __name__ == "__main__":
    main(*sys.argv[1:])
