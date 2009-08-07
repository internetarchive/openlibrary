# get set of meta tag names to exclude from solr slop field
from xml.etree.ElementTree import ElementTree as ET
from os.path import abspath, dirname

current_dir = abspath(dirname(__file__))

schema_filename = '%s/../../conf/solr-biblio/conf/schema.xml'% current_dir
_schema_xmltree = None

def _checkfields(fieldname, attrname, pred, resultname):
    global _schema_xmltree
    if _schema_xmltree is None:
        _schema_xmltree = ET().parse(schema_filename)

    def m():
        for e in _schema_xmltree.getiterator(fieldname):
            a = e.get(attrname)
            if a and pred(a):
                yield e.get(resultname)
    return set(m())
                
excluded_fields = _checkfields('excludedFieldForUnspecifiedSearch',
                               'name',
                               bool,
                               'name')

multivalued_fields = _checkfields('field',
                                  'multiValued',
                                  lambda a: str(a)=='true',
                                  'name')
    
all_fields = _checkfields('field', 'name', lambda a: True, 'name')

singleton_fields = all_fields - multivalued_fields

if __name__ == "__main__":
    print 'excluded:', sorted(excluded_fields)
    print 'multi:', sorted(multivalued_fields)
    print 'all:', sorted(all_fields)
    print 'singleton:', sorted(singleton_fields)
