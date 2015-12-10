"""Interface to update solr.
"""
import httplib
import logging
import re

from lxml.etree import tostring, Element
from unicodedata import normalize

logger = logging.getLogger("openlibrary.solrwriter")

class SolrWriter(object):
    """Interface to update solr.
    """
    def __init__(self, host, core=None):
        self.host = host
        if core:
            self.update_url = "/solr/%s/update" % core
        else:
            self.update_url = "/solr/update"

        self.conn = None
        self.identifier_field = "key"
        self.pending_updates = []

    def get_conn(self):
        if self.conn is None:
            self.conn = httplib.HTTPConnection(self.host)
        return self.conn

    def request(self, xml):
        """Sends an update request to solr with given XML.
        """
        conn = self.get_conn()

        logger.info('request: %r', xml[:65] + '...' if len(xml) > 65 else xml)
        conn.request('POST', self.update_url, xml, { 'Content-type': 'text/xml;charset=utf-8'})
        response = conn.getresponse()
        response_body = response.read()

        logger.info(response.reason)
        if response.reason != 'OK':
            logger.error(response_body)
        assert response.reason == 'OK'

    def delete(self, key):
        logger.info("deleting %s", key)
        q = '<delete><id>%s</id></delete>' % key
        self.request(q)

    def update(self, document):        
        logger.info("updating %s", document.get(self.identifier_field))
        self.pending_updates.append(document)
        if len(self.pending_updates) >= 100:
            self.flush()
        return

    def flush(self):
        if self.pending_updates:
            root = Element("add")
            for doc in self.pending_updates:
                node = dict2element(doc)
                root.append(node)
            logger.info("flushing %d documents", len(self.pending_updates))
            self.pending_updates = []
            xml = tostring(root).encode('utf-8')
            self.request(xml)

    def commit(self):
        self.flush()
        logger.info("<commit/>")
        self.request("<commit/>")

    def optimize(self):
        logger.info("<optimize/>")
        self.request("<optimize/>")

re_bad_char = re.compile('[\x01\x0b\x1a-\x1e]')
def strip_bad_char(s):
    if not isinstance(s, basestring):
        return s
    return re_bad_char.sub('', s)

def add_field(doc, name, value):
    if isinstance(value, (list, set)):
        for v in value:
            add_field(doc, name, v)
        return
    else:
        field = Element("field", name=name)
        if not isinstance(value, basestring):
            value = str(value)
        try:
            value = strip_bad_char(value)
            if isinstance(value, str):
                value = value.decode('utf-8')
            field.text = normalize('NFC', value)
        except:
            logger.error('Error in normalizing %r', value)
            raise
        doc.append(field)

def dict2element(d):
    doc = Element("doc")
    for k, v in d.items():
        add_field(doc, k, v)
    return doc
