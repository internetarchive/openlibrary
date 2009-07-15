#! /usr/bin/env python
import sys
import tarfile

def get_index(tar):
    for tarinfo in tar.getmembers():
        yield "%s\t%s\t%s\n" % (tarinfo.name, tarinfo.offset_data, tarinfo.size)

for f in sys.argv[1:]:
    print f
    t = tarfile.TarFile(f)
    out = open(f.replace('.tar', '.index'), 'w')
    out.writelines(get_index(t))
    out.close()