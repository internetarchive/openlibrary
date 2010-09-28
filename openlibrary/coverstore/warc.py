"""
Reader and writer for WARC file format version 0.10.

http://archive-access.sourceforge.net/warc/warc_file_format-0.10.html
"""

import urllib
import httplib
import datetime

WARC_VERSION = "0.10"
CRLF = "\r\n"

class WARCReader:
    """Reader to read records from a warc file.
    
    >>> import StringIO
    >>> f = StringIO.StringIO()
    >>> r1 = WARCRecord("resource", "subject_uri", "image/jpeg", {"hello": "world"}, "foo")
    >>> r2 = WARCRecord("resource", "subject_uri", "image/jpeg", {"hello": "world"}, "bar")
    >>> w = WARCWriter(f)
    >>> _ = w.write(r1)
    >>> _ = w.write(r2)
    >>> f.seek(0)
    >>> reader = WARCReader(f)
    >>> records = list(reader.read())
    >>> records == [r1, r2]
    True
    """
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
    r"""WARCHeader class represents the header in the WARC file format.
    
    header      = header-line CRLF *anvl-field CRLF
    header-line = warc-id tsp data-length tsp record-type tsp
                  subject-uri tsp creation-date tsp
                  record-id tsp content-type
    anvl-field  =  field-name ":" [ field-body ] CRLF
    
    >>> WARCHeader("WARC/0.10", 10, "resource", "subject_uri", "20080808080808", "record_42", "image/jpeg", {'hello': 'world'})
    <header: 'WARC/0.10 10 resource subject_uri 20080808080808 record_42 image/jpeg\r\nhello: world\r\n\r\n'>
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

    def dict(self):
        d = dict(self.headers)
        for k in ["warc_id", "data_length", "record_type", "subject_uri", "creation_date", "record_id", "content_type"]:
            d[k] = getattr(self, k)
        return d
        
    def __repr__(self):
        return "<header: %s>" % repr(str(self))

class WARCRecord:
    r"""A record in a WARC file.
    
    >>> WARCRecord("resource", "subject_uri", "image/jpeg", {"hello": "world"}, "foo bar", creation_date="20080808080808", record_id="record_42")
    <record: 'WARC/0.10 7 resource subject_uri 20080808080808 record_42 image/jpeg\r\nhello: world\r\n\r\nfoo bar'>
    """
    def __init__(self, record_type, subject_uri, content_type, headers, data, creation_date=None, record_id=None):        
        warc_id = "WARC/" + WARC_VERSION
        data_length = len(data)
        creation_date = creation_date or datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')
        record_id = record_id or self.create_uuid()
        
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
        
    def __repr__(self):
        return "<record: %s>" % repr(str(self))
        
class LazyWARCRecord(WARCRecord):
    """Class to create WARCRecord lazily.
    
    >>> import StringIO
    >>> r1 = WARCRecord("resource", "subject_uri", "image/jpeg", {"hello": "world"}, "foo bar", creation_date="20080808080808", record_id="record_42")
    >>> f = StringIO.StringIO(str(r1))
    >>> offset = len(str(r1.get_header()))
    >>> r2 = LazyWARCRecord(f, offset, r1.get_header())
    >>> r1 == r2
    True
    """
    def __init__(self, file, offset, header):
        self.header = header
        self.file = file
        self.offset = offset
        self._data = None
        
    def get_header(self):
        return self.header
        
    def get_data(self):
        if self._data is None:
            offset = self.file.tell()
            self.file.seek(int(self.offset))
            self._data = self.file.read(int(self.header.data_length))
            self.file.seek(offset)
        return self._data

class WARCWriter:
    r"""Writes to write warc records to file.
    
    >>> import re, StringIO
    >>> f = StringIO.StringIO()
    >>> r1 = WARCRecord("resource", "subject_uri", "image/jpeg", {"hello": "world"}, "foo", creation_date="20080808080808", record_id="record_42")
    >>> r2 = WARCRecord("resource", "subject_uri", "image/jpeg", {"hello": "world"}, "bar", creation_date="20080808090909", record_id="record_43")
    >>> w = WARCWriter(f)
    >>> w.write(r1)
    86
    >>> w.write(r2)
    179
    >>> lines = re.findall('[^\r\n]*\r\n', f.getvalue()) # break at \r\n to print in a readable way
    >>> for line in lines: print repr(line)
    'WARC/0.10 3 resource subject_uri 20080808080808 record_42 image/jpeg\r\n'
    'hello: world\r\n'
    '\r\n'
    'foo\r\n'
    '\r\n'
    'WARC/0.10 3 resource subject_uri 20080808090909 record_43 image/jpeg\r\n'
    'hello: world\r\n'
    '\r\n'
    'bar\r\n'
    '\r\n'
    """
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
    import doctest
    doctest.testmod()
