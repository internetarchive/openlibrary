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

    def get_conn(self):
        if self.conn is None:
            self.conn = httplib.HTTPConnection(self.host)
        return self.conn

    def request(self, xml):
        """Sends an update request to solr with given XML.
        """
        conn = self.get_conn()

        logger.debug('request: %r', xml[:65] + '...' if len(xml) > 65 else xml)
        conn.request('POST', self.update_url, xml, { 'Content-type': 'text/xml;charset=utf-8'})
        response = conn.getresponse()
        response_body = response.read()

        logger.info(response.reason)
        if response.reason != 'OK':
            logger.error(response_body)
        assert response.reason == 'OK'

    def update(self, document):
        logger.info("updating %s", document.get(self.identifier_field))
        node = dict2element(document)
        root = Element("add")
        root.append(node)
        xml = tostring(root).encode('utf-8')
        self.request(xml)

    def commit(self):
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
        try:
            field.text = normalize('NFC', unicode(strip_bad_char(value)))
        except:
            logger.error('Error in normalizing %r', value)
            raise
        doc.append(field)

def dict2element(d):
    doc = Element("doc")
    for k, v in d.items():
        add_field(doc, k, v)
    return doc
