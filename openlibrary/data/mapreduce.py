"""Simple library to process large datasets using map-reduce.

This works as follows:

* Takes an iterator of key-value pairs as input
* Applies the map function for each key-value pair. The map function does the
  required processing to yield zero or more key-value pairs.
* The result of map are stored in the disk in to multiple files based on the 
  hash of the key. This makes sure the all the entries with same key goes to 
  the same file.
* Each of the file is sorted on key to group all the values of a key and the
  reduce function is applied for each key and its values. 
* The reduced key, value pairs are returned as an iterator.
"""
import sys
import itertools
import os
import subprocess
import logging
import gzip

logger = logging.getLogger("mapreduce")

class Task:
    """Abstraction of a map-reduce task.

    Each task should extend this class and implement map and reduce functions.
    """
    def __init__(self, tmpdir="mapreduce", filecount=100, hashfunc=None):
        self.tmpdir = tmpdir
        self.filecount = 100
        self.hashfunc = None

    def map(self, key, value):
        """Function to map given key-value pair into zero or more key-value pairs.
        
        The implementation should yield the key-value pairs.
        """
        raise NotImplementedError()

    def reduce(self, key, values):
        """Function to reduce given values.
        
        The implementation should return a key-value pair, with the reduced value.
        """
        raise NotImplementedError()
        
    def read(self):
        for line in sys.sydin:
            key, value = line.strip().split("\t", 1)
            yield key, value
            
    def map_all(self, records, disk):
        for key, value in records:
            for k, v in self.map(key, value):
                disk.write(k, v)
        disk.close()
                
    def reduce_all(self, records):
        for key, chunk in itertools.groupby(records, lambda record: record[0]):
            values = [value for key, value in chunk]
            yield self.reduce(key, values)

    def process(self, records):
        """Takes key-value pairs, applies map-reduce and returns the resultant key-value pairs.
        """
        # Map the record and write to disk
        disk = Disk(self.tmpdir, mode="w", hashfunc=self.hashfunc)
        self.map_all(records, disk)
        disk.close()
        
        # Read from the disk in the sorted order and reduce
        disk = Disk(self.tmpdir, mode="r", hashfunc=self.hashfunc)
        records = disk.read_semisorted()
        return self.reduce_all(records)
                
class Disk:
    """Map Reduce Disk to manage key values.
    
    The data is stored over multiple files based on the key. All records with same key will fall in the same file.
    """
    def __init__(self, dir, prefix="shard", filecount=100, hashfunc=None, mode="r"):
        self.dir = dir
        self.prefix = prefix
        self.hashfunc = hashfunc or (lambda key: hash(key))        
        self.buffersize = 1024 * 1024
        
        if not os.path.exists(dir):
            os.makedirs(dir)
        self.files = [self.openfile(i, mode) for i in range(filecount)]
        
    def openfile(self, index, mode):
        filename = "%s-%03d.txt.gz" % (self.prefix, index)
        path = os.path.join(self.dir, filename)
        return gzip.open(path, mode)

    def write(self, key, value):
        index = self.hashfunc(key) % len(self.files)
        f = self.files[index]
        f.write(key + "\t" + value + "\n")
    
    def close(self):
        for f in self.files:
            f.close()
            
    def read_semisorted(self):
        """Sorts each file in the disk and returns an iterator over the key-values in each file. 

        All the values with same key will come together as each file is sorted, but there is no guaranty on the global order of keys.
        """
        for f in self.files:
            cmd = "gzip -cd %s | sort -S1G" % f.name
            logger.info(cmd)
            p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
            for line in p.stdout:
                key, value = line.split("\t", 1)
                yield key, value
            status = p.wait()
            if status != 0:
                raise Exception("sort failed with status %d" % status)

