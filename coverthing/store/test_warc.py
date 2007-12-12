
import warc
import unittest
from StringIO import StringIO


def FakeHTTPFile(data, chunk_size=None):
    f = StringIO(data)
    httpfile = warc.HTTPFile(None, chunk_size)
    httpfile.tell = f.tell
    httpfile.seek = f.seek
    httpfile.read = f.read
    return httpfile

class WARCReaderTest(unittest.TestCase):
    def test_read(self):
        def make_data(index, data):
            return ('WARC/1.0 %d resource subject%d date%d id%d type%d\r\n' +
                    'key%d: value%d\r\n'+
                    '\r\n' + \
                    data + \
                    '\r\n\r\n') % (len(data), index, index, index, index, index, index)

        data = make_data(1, 'ab') + make_data(2, 'hello, world!')
        
        file = StringIO(data)        
        reader = warc.WARCReader(file)
        records = list(reader.read())
        
        self.assertEquals(len(records), 2)
        r1, r2 = records
        
        self.assertEquals(r1.get_data(), 'ab')
        self.assertEquals(r2.get_data(), 'hello, world!')
        
class WARCHeaderTest(unittest.TestCase):
    def test_eq(self):
        h1 = warc.WARCHeader('WARC/1.0', 10, "resource", "http://warc/test/1", "date1", "uid:1", "text/plain", {'k1': 'v1'})
        h2 = warc.WARCHeader('WARC/1.0', 10, "resource", "http://warc/test/1", "date1", "uid:1", "text/plain", {'k1': 'v1'})
        self.assertEquals(h1, h2)
        
class WARCRecord(unittest.TestCase):
    def test_eq(self):
        r1 = warc.WARCRecord("resource", "http://warc/test/1", "text/plain", {'k1': 'v1'}, "hello, world!")
        r2 = warc.WARCRecord("resource", "http://warc/test/1", "text/plain", {'k1': 'v1'}, "hello, world!")
        r2.get_header().record_id = r1.get_header().record_id
        
        self.assertEquals(r1, r2)

class WARCWriterTest(unittest.TestCase):
    def test_writer(self):
        r1 = warc.WARCRecord("resource", "http://warc/test/1", "text/plain", {}, "hello, world!")
        r2 = warc.WARCRecord("resource", "http://warc/test/2", "text/plain", {'k1': 'v1', 'k2': 'v2'}, "warc test")
        
        file = StringIO()
        w = warc.WARCWriter(file)
        w.write(r1)
        w.write(r2)
        file.seek(0)
        r = warc.WARCReader(file)
        records = list(r.read())
        self.assertEquals(records[0], r1)
        self.assertEquals(records[1], r2)

class HTTPFileTest(unittest.TestCase):
    def test_readline(self):
        data = 'one\ntwo\nthree\n'
        for chunk_size in [1, 2, 4, 8, 16, 32]:
            f = FakeHTTPFile(data, chunk_size=chunk_size)
            self.assertEquals(f.readline(), 'one\n')
            self.assertEquals(f.readline(), 'two\n')
            self.assertEquals(f.readline(), 'three\n')
            self.assertEquals(f.readline(), '')
            self.assertEquals(f.readline(), '')
            
def suite():
    classes = [v for v in globals().values() if isinstance(v, unittest.TestSuite)]
    suites = [unittest.makeSuite(c) for c in classes]
    return unittest.TestSuite(suites)

if __name__ == '__main__':
    import unittest
    unittest.main()
