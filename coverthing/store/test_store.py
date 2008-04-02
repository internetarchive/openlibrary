import unittest
import tempfile
import random
import string
import os, shutil

import store
import disk

class StoreTest(unittest.TestCase):
    def unique_prefix(self):
        # to make each test unique
        return "".join([random.choice(string.letters) for i in range(10)]) + "_"
        
    def test_store(self):
        s = store.Store(self.make_disk())
        prefix = self.unique_prefix()
        
        a = {prefix + 'x': 'foo', prefix + 'y': 'bar'}
        id_a = s.save(a)
        self.assertEquals(a, s.get(id_a))
        self.assertEquals(s.query(a), [id_a])
        self.assertEquals(s.query({prefix + 'y': 'bar'}), [id_a])
        
        b = {prefix + 'x': 'foo', prefix + 'y': 'barbar'}
        id_b = s.save(b)
        self.assertEquals(b, s.get(id_b))
        self.assertEquals(s.query(b), [id_b])
        self.assertEquals(s.query({prefix + 'y': 'barbar'}), [id_b])
        
        self.assertEquals(sorted(s.query({prefix + 'x': 'foo'})), [id_a, id_b])        
        self.clean_disk(s.disk)
        
    def test_files(self):
        s = store.Store(self.make_disk())
        prefix = self.unique_prefix()
        
        a = { prefix + 'x': 'foo', prefix + 'y': store.File('bar')}
        id_a = s.save(a)        
        self.assertEquals(a, s.get(id_a))
        
        self.clean_disk(s.disk)
        
    def make_disk(self):
        return disk.Disk(tempfile.mkdtemp())
        
    def clean_disk(self, disk):
        shutil.rmtree(disk.root)
        
class StoreTestWithWARCDisk(StoreTest):
    def make_disk(self):
        return disk.WARCDisk(tempfile.mkdtemp())

def suite():
    import web
    web.config.db_parameters = dict(dbn='postgres', db='store_test', user='anand', pw='')
    web.load()
    classes = [StoreTest, StoreTestWithWARCDisk]
    suites = [unittest.makeSuite(c) for c in classes]
    return unittest.TestSuite(suites)

if __name__ == '__main__':
    import web
    web.config.db_parameters = dict(dbn='postgres', db='store_test', user='anand', pw='')
    web.load()
    unittest.main()
