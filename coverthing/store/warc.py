"""
Reader and writer for WARC file format.

http://archive-access.sourceforge.net/warc/warc_file_format.html
"""

import urllib
import httplib
import datetime

WARC_VERSION = "0.10"
CRLF = "\r\n"

class WARCReader:
    def __init__(self, file):
        self._file = file
        
    def read(self):
        """Returns an iterator over all the records in the WARC file."""
        def consume_crlf():
            assert self._readline() == CRLF

        while True:
            header = self._read_header()
            if header is None:
                break
            yield LazyWARCRecord(self._file, self._file.tell(), header)
            self._file.seek(int(header.data_length), 1)
            consume_crlf()
            consume_crlf()

    def _read_header(self):
        """Reads the header of a record from the WARC file."""
        def consume_crlf():
            line = self._file.readline()
            assert line == CRLF

        line = self._file.readline()
        if not line: 
            return None
        
        tokens = line.strip().split()
        warc_id, data_length, record_type, subject_uri, creation_date, record_id, content_type = tokens
        header = WARCHeader(warc_id, 
            data_length, record_type, subject_uri, 
            creation_date, record_id, content_type, {})
            
        while True:
            line = self._file.readline()
            if line == CRLF:
                break
            k, v = line.strip().split(':', 1)
            header.headers[k.strip()] = v.strip()
        return header
        
    def _readline(self):        
        line = self._file.readline()
        if line[-2:-1] == '\r':
            return line
        else:
            return line + self._readline()

class HTTPFile:
    """File like interface to HTTP url."""
    def __init__(self, url, chunk_size=1024):
        self.url = url
        self.offset = 0
        self.chunk_size = chunk_size
        
    def seek(self, offset, whence=0):
        if whence == 0:
            self.offset = offset
        elif whence == 1:
            self.offset += offset
        else:
            raise "Invalid whence", whence
    
    def tell(self):
        return self.offset
        
    def readline(self):
        """Reads a line from file."""
        data = ''
        offset = self.tell()
        data = "".join(self._readuntil(lambda chunk: '\n' in chunk or chunk == ''))
        data = data[:data.find('\n') + 1]
        self.seek(offset + len(data))
        return data

    def _readuntil(self, condition):
        while True:
            data = self.read(self.chunk_size)
            yield data
            if condition(data):
                break     

    def read(self, size):
        protocol, host, port, path = self.urlsplit(self.url)
        conn = httplib.HTTPConnection(host, port)
        headers = {'Range': 'bytes=%d-%d' % (self.offset, self.offset + size - 1)}
        conn.request('GET', path, None, headers)
        response = conn.getresponse()
        data = response.read()
        self.offset += len(data)
        return data
            
    def urlsplit(self, url):
        """Splits url into protocol, host, port and path.

            >>> f = HTTPFile('')
            >>> f.urlsplit("http://www.google.com/search?q=hello")
            ('http', 'www.google.com', None, '/search?q=hello')
        """
        protocol, rest = urllib.splittype(url)
        hostport, path = urllib.splithost(rest)
        host, port = urllib.splitport(hostport)
        return protocol, host, port, path        
    
class WARCHeader:
    """WARCHeader class represents the header in the WARC file format.
    """
    def __init__(self, warc_id, 
            data_length, record_type, subject_uri, 
            creation_date, record_id, content_type, headers):
        self.warc_id = warc_id
        self.data_length = str(data_length)
        self.record_type = record_type
        self.subject_uri = subject_uri
        self.creation_date = creation_date
        self.record_id = record_id
        self.content_type = content_type
        self.headers = headers
        
    def __eq__(self, other):
        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        return not (self == other)
        
    def __str__(self):
        params = [self.warc_id, self.data_length, self.record_type, self.subject_uri, 
                self.creation_date, self.record_id, self.content_type]
                
        a = " ".join([str(p) for p in params]) 
        b = "".join(["%s: %s\r\n" % (k, v) for k, v in self.headers.items()])
        return a + CRLF + b + CRLF
        
    def __repr__(self):
        return "<header: %s>" % repr(str(self))

class WARCRecord:
    """A record in a WARC file. 
    """
    def __init__(self, record_type, subject_uri, content_type, headers, data):        
        warc_id = "WARC/" + WARC_VERSION
        data_length = len(data)
        creation_date = datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')
        record_id = self.create_uuid()
        
        self._header = WARCHeader(warc_id, data_length, record_type, subject_uri, 
                                creation_date, record_id, content_type, headers)
        self._data = data

    def create_uuid(self):
        import uuid
        return 'urn:uuid:' + str(uuid.uuid1())
        
    def get_header(self):
        return self._header
        
    def get_data(self):
        return self._data
        
    def __eq__(self, other):
        return self.get_header() == other.get_header() and self.get_data() == other.get_data()
        
    def __ne__(self, other):
        return not (self == other)
        
    def __str__(self):
        return str(self.get_header()) + self.get_data()
        
class LazyWARCRecord(WARCRecord):
    def __init__(self, file, offset, header):
        self.header = header
        self.file = file
        self.offset = offset
        self._data = None
        
    def get_header(self):
        return self.header
        
    def get_data(self):
        if self._data is None:
            self.file.seek(int(self.offset))
            self._data = self.file.read(int(self.header.data_length))
        return self._data

class WARCWriter:
    def __init__(self, file):
        self.file = file
        
    def close(self):
        self.file.close()
        
    def write(self, record):
        """Writes a record into the WARC file. 
        Assumes that data_length and other attributes are correctly set in record.header.
        """
        self.file.write(str(record.get_header()))
        offset = self.file.tell()
        self.file.write(record.get_data())
        self.file.write(CRLF + CRLF)
        self.file.flush()
        return offset

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '-t':
        import doctest
        doctest.testmod()
    else:
        r1 = WARCRecord("resource", "file:///tmp/a.txt", "text/plain", {'a': 42}, "hello, world!")
        r2 = WARCRecord("resource", "file:///tmp/life.txt", "text/plain", {'x': 32}, "Life is suffering")
        w = WARCWriter("/tmp/a.warc", "w")
        w.write(r1)
        w.write(r2)
        w.close()
    
        r = LocalWARCReader('/tmp/a.warc')
        for r in r.records():
            print r
