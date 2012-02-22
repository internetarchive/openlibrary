#! /usr/bin/env python
"""Script to delete cover permanantly from coverstore.

Used when some assert copyright on an images and demands to remove it from our collection.

USAGE:
    
    python scripts/2012/02/delete-cover.py 5699220

After deleting the item must be uploaded back to archive.org cluster. This can be done using:

    /olsystem/bin/uploaditem.py --u

    
"""
import os
import sys

def download(itemid, filename):
    os.system("mkdir -p " + itemid)
    os.system("wget -nv http://www.archive.org/download/%(itemid)s/%(filename)s -O %(itemid)s/%(filename)s" % locals())

def delete_cover(itemid, zipfile, filename):
    download(itemid, zipfile)
    os.system("7z d %(filename)s %(itemid)s/%(zipfile)s" % locals())

def main():
    coverid = int(sys.argv[1])
    itemid = "olcovers%d" % (coverid/10000) 

    download(itemid, itemid + "_meta.xml")

    for suffix in ["-S", "-M", "-L", ""]:
        zipfile = itemid + suffix + ".zip"
        imgfile = str(coverid) + suffix + ".jpg"
        delete_cover(itemid, zipfile, imgfile)

if __name__ == "__main__":
    main()
