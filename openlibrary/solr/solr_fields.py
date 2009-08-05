# get set of meta tag names to exclude from solr slop field
from xml.etree.ElementTree import ElementTree as ET

# _schema_file = ET().parse('/home/phr/petabox/solr/example/solr/conf/schema.xml')
_schema_file = ET().parse('solr-schema.xml')

def _checkfields(fieldname, attrname, pred, resultname):
    def m():
        for e in _schema_file.getiterator(fieldname):
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
