"""Library for interacting wih archive.org.
"""
import urllib2
from xml.dom import minidom
import web

from infogami.utils import stats

def get_meta_xml(itemid):
    """Returns the contents of meta_xml as JSON.
    """
    url = 'http://www.archive.org/download/%s/%s_meta.xml' % (itemid, itemid)
    try:
        stats.begin("archive.org", url=url)
        metaxml = urllib2.urlopen(url).read()
        stats.end()
    except IOError:
        stats.end()
        return web.storage()
        
    return web.storage(xml2dict(metaxml, collection=set()))
        
def xml2dict(xml, **defaults):
    """Converts xml to python dictionary assuming that the xml is not nested.
    
    To get some tag as a list/set, pass a keyword argument with list/set as value.
    
        >>> xml2dict('<doc><x>1</x><x>2</x></doc>')
        {'x': 2}
        >>> xml2dict('<doc><x>1</x><x>2</x></doc>', x=[])
        {'x': [1, 2]}
    """
    d = defaults
    dom = minidom.parseString(xml)
    
    for node in dom.documentElement.childNodes:
        if node.nodeType == node.TEXT_NODE:
            continue
        else:
            key = node.tagName
            value = node.childNodes[0].data
            
            if key in d and isinstance(d[key], list):
                d[key].append(value)
            elif key in d and isinstance(d[key], set):
                d[key].add(value)
            else:
                d[key] = value
                
    return d
