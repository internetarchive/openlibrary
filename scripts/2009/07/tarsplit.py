"""In the process of moving coverstore images into tar files, 
one tar file for each warc file has been created with original, 
small, medium and large images in them.

This script splits them into separate tar files each containing only
one type of images and contain exactly 10K images.
"""
import sys
import tarfile
import web
import os.path

logfile = open('log.txt', 'a')

def log(*args):
    msg = " ".join(args)
    print msg
    print >> logfile, msg
    logfile.flush()

class TarManager:
    def __init__(self):
        self.tarfiles = {}
        self.tarfiles[''] = (None, None)
        self.tarfiles['S'] = (None, None)
        self.tarfiles['M'] = (None, None)
        self.tarfiles['L'] = (None, None)

    def get_tarfile(self, name):
        id = web.numify(name)
        prefix = "covers_%s_%s" % (id[:4], id[4:6])

        if '-' in name:
            size = name.split('-')[1].split('.')[0]
            tarname = size.lower() + "_" + prefix + ".tar"
        else:
            size = ''
            tarname = prefix + ".tar"

        _tarname, _tarfile = self.tarfiles[size]
        if _tarname != tarname:
            _tarname and _tarfile.close()
            _tarfile = self.open_tarfile(tarname)
            self.tarfiles[size] = tarname, _tarfile
            log('writing', tarname)

        return _tarfile

    def open_tarfile(self, name):
        path = "out/" + name
        if os.path.exists(path):
            log('WARNING: Appending to ', path)
            return tarfile.TarFile(path, 'a')
        else:
            return tarfile.TarFile(path, 'w')

    def add_file(self, name, fileobj, mtime):
        tarinfo = tarfile.TarInfo(name)
        tarinfo.mtime = mtime
        tarinfo.size = fileobj.size
        
        self.get_tarfile(name).addfile(tarinfo, fileobj=fileobj)

    def close(self):
        for name, _tarfile in self.tarfiles.values():
            if name:
                print 'closing', name
                _tarfile.close()

def main(files):
    tar_manager = TarManager()

    for f in files:
        log("reading ", f)
        # open in append mode and close it to make sure EOF headers are written correctly.
        #_tarfile = tarfile.TarFile(f, 'a')
        #_tarfile.close()
        
        _tarfile = tarfile.TarFile(f)
        try:
            for tarinfo in _tarfile:
                name = tarinfo.name
                mtime = tarinfo.mtime
                fileobj = _tarfile.extractfile(tarinfo)

                if name.endswith('-O.jpg'):
                    name = name.replace('-O', '')

                tar_manager.add_file(name, fileobj, mtime)
        except Exception, e:
            import traceback
            traceback.print_exc()
            log("Error", str(e))

    logfile.close()
    tar_manager.close()
            
if __name__ == "__main__":
    main(sys.argv[1:])
