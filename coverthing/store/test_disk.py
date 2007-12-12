import disk
import unittest
import tempfile

class DiskTest(unittest.TestCase):
    def test_disk(self):
        disk = self.create_disk()
        
        def _test(filename, data):
            disk.write(filename, data)
            self.testEquals(disk.read(filename), data)

        # try read-write
        disk.write('a.txt', 'hello, world!')
        self.assertEquals(disk.read('a.txt'), 'hello, world!')
        
        # try empty data
        disk.write('b.txt', '')
        self.assertEquals(disk.read('b.txt'), '')
        
        # try special chars
        disk.write('c.txt', 'a\nb\r\nc\n')
        self.assertEquals(disk.read('c.txt'), 'a\nb\r\nc\n')
        
        # try overwrite
        disk.write('a.txt', 'foo')
        disk.write('a.txt', 'bar')
        self.assertEquals(disk.read('a.txt'), 'bar')
        
    def create_disk(self):
        root = tempfile.mkdtemp()
        return disk.Disk(root)
        
class WARCDiskTest(DiskTest):
    def create_disk(self):
        root = tempfile.mkdtemp()
        print root
        return disk.WARCDisk(root)
        
def suite():
    classes = [DiskTest, WARCDiskTest]
    suites = [unittest.makeSuite(c) for c in classes]
    return unittest.TestSuite(suites)

if __name__ == "__main__":
    import unittest
    unittest.main()
