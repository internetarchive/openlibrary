"""
Reader and writer for WARC file format version 0.10.

http://archive-access.sourceforge.net/warc/warc_file_format-0.10.html
"""

import datetime

from six.moves.http_client import HTTPConnection
from six.moves.urllib.parse import urlparse

WARC_VERSION = "0.10"
CRLF = "\r\n"


class WARCHeader:
    r"""WARCHeader class represents the header in the WARC file format.

    header      = header-line CRLF *anvl-field CRLF
    header-line = warc-id tsp data-length tsp record-type tsp
                  subject-uri tsp creation-date tsp
                  record-id tsp content-type
    anvl-field  =  field-name ":" [ field-body ] CRLF

    >>> WARCHeader("WARC/0.10", 10, "resource", "subject_uri", "20080808080808", "record_42", "image/jpeg", {'hello': 'world'})
    <header: 'WARC/0.10 10 resource subject_uri 20080808080808 record_42 image/jpeg\r\nhello: world\r\n\r\n'>
    >>> WARCHeader("WARC/0.10", b"10", "resource", "subject_uri", "20080808080808", "record_42", "image/jpeg", {'hello': 'world'})
    <header: 'WARC/0.10 10 resource subject_uri 20080808080808 record_42 image/jpeg\r\nhello: world\r\n\r\n'>
    """
    def __init__(self, warc_id,
            data_length, record_type, subject_uri,
            creation_date, record_id, content_type, headers):
        self.warc_id = warc_id
        self.data_length = str(int(data_length))  # deal with bytes, int, and str
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

    >>> from six import StringIO
    >>> r1 = WARCRecord("resource", "subject_uri", "image/jpeg", {"hello": "world"}, "foo bar", creation_date="20080808080808", record_id="record_42")
    >>> f = StringIO(str(r1))
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

    >>> import re
    >>> from six import StringIO
    >>> f = StringIO()
    >>> r1 = WARCRecord("resource", "subject_uri", "image/jpeg", {"hello": "world"}, "foo", creation_date="20080808080808", record_id="record_42")
    >>> r2 = WARCRecord("resource", "subject_uri", "image/jpeg", {"hello": "world"}, "bar", creation_date="20080808090909", record_id="record_43")
    >>> w = WARCWriter(f)
    >>> w.write(r1)
    86
    >>> w.write(r2)
    179
    >>> lines = re.findall('[^\r\n]*\r\n', f.getvalue()) # break at \r\n to print in a readable way
    >>> for line in lines: print(repr(line))
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
