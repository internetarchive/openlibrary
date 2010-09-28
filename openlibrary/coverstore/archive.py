"""Utility to move files from local disk to tar files and update the paths in the db.
"""
import sys
import tarfile
import web
import os
import time

from openlibrary.coverstore import config, db
from openlibrary.coverstore.coverlib import ensure_thumbnail_created, find_image_path

#logfile = open('log.txt', 'a')

def log(*args):
    msg = " ".join(args)
    print msg
    #print >> logfile, msg
    #logfile.flush()

class TarManager:
    def __init__(self):
        self.tarfiles = {}
        self.tarfiles[''] = (None, None, None)
        self.tarfiles['S'] = (None, None, None)
        self.tarfiles['M'] = (None, None, None)
        self.tarfiles['L'] = (None, None, None)

    def get_tarfile(self, name):
        id = web.numify(name)
        tarname = "covers_%s_%s.tar" % (id[:4], id[4:6])
                
        # for id-S.jpg, id-M.jpg, id-L.jpg
        if '-' in name: 
            size = name[len(id + '-'):][0].lower()
            tarname = size + "_" + tarname
        else:
            size = ""
        
        _tarname, _tarfile, _indexfile = self.tarfiles[size.upper()]
        if _tarname != tarname:
            _tarname and _tarfile.close()
            _tarfile, _indexfile = self.open_tarfile(tarname)
            self.tarfiles[size.upper()] = tarname, _tarfile, _indexfile
            log('writing', tarname)

        return _tarfile, _indexfile

    def open_tarfile(self, name):
        path = os.path.join(config.data_root, "items", name[:-len("_XX.tar")], name)
        dir = os.path.dirname(path)
        if not os.path.exists(dir):
            os.makedirs(dir)
            
        indexpath = path.replace('.tar', '.index')
            
        if os.path.exists(path):
            return tarfile.TarFile(path, 'a'), open(indexpath, 'a')
        else:
            return tarfile.TarFile(path, 'w'), open(indexpath, 'w')

    def add_file(self, name, fileobj, mtime):
        tarinfo = tarfile.TarInfo(name)
        tarinfo.mtime = mtime
        tarinfo.size = os.stat(fileobj.name).st_size
        
        tar, index = self.get_tarfile(name)
        # tar.offset is current size of tar file. 
        # Adding 512 bytes for header gives us the starting offset of next file.
        offset = tar.offset + 512
        
        tar.addfile(tarinfo, fileobj=fileobj)
        
        index.write('%s\t%s\t%s\n' % (name, offset, tarinfo.size))
        return "%s:%s:%s" % (os.path.basename(tar.name), offset, tarinfo.size)

    def close(self):
        for name, _tarfile, _indexfile in self.tarfiles.values():
            if name:
                _tarfile.close()
                _indexfile.close()
idx = id
def archive():
    """Move files from local disk to tar files and update the paths in the db."""
    tar_manager = TarManager()
    
    _db = db.getdb()

    try:
        covers = _db.select('cover', where='archived=$f', order='id', vars={'f': False})
        for cover in covers:
            id = "%010d" % cover.id

            print 'archiving', cover
            
            files = {
                'filename': web.storage(name=id + '.jpg', filename=cover.filename),
                'filename_s': web.storage(name=id + '-S.jpg', filename=cover.filename_s),
                'filename_m': web.storage(name=id + '-M.jpg', filename=cover.filename_m),
                'filename_l': web.storage(name=id + '-L.jpg', filename=cover.filename_l),
            }
            # required until is coverstore is completely migrated to new code.
            ensure_thumbnail_created(cover.id, find_image_path(cover.filename))
            
            for d in files.values():
                d.path = d.filename and os.path.join(config.data_root, "localdisk", d.filename)
                    
            if any(d.path is None or not os.path.exists(d.path) for d in files.values()):
                print >> web.debug, "Missing image file for %010d" % cover.id
                continue
            
            if isinstance(cover.created, basestring):
                from infogami.infobase import utils
                cover.created = utils.parse_datetime(cover.created)    
            
            timestamp = time.mktime(cover.created.timetuple())
                
            for d in files.values():
                d.newname = tar_manager.add_file(d.name, open(d.path), timestamp)
                
            _db.update('cover', where="id=$cover.id",
                archived=True, 
                filename=files['filename'].newname,
                filename_s=files['filename_s'].newname,
                filename_m=files['filename_m'].newname,
                filename_l=files['filename_l'].newname,
                vars=locals()
            )
        
            for d in files.values():
                print 'removing', d.path            
                os.remove(d.path)
    finally:
        #logfile.close()
        tar_manager.close()
