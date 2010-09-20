"""Infobase schema for Open Library
"""
from infogami.infobase import dbstore
import web

def get_schema():
    schema = dbstore.Schema()
    schema.add_table_group('type', '/type/type')
    schema.add_table_group('type', '/type/property')
    schema.add_table_group('type', '/type/backreference')
    schema.add_table_group('user', '/type/user')
    schema.add_table_group('user', '/type/usergroup')
    schema.add_table_group('user', '/type/permission')
    
    datatypes = ["str", "int", "ref", "boolean"]
    
    schema.add_table_group('edition', '/type/edition', datatypes)
    schema.add_table_group('author', '/type/author', datatypes)
    schema.add_table_group('scan', '/type/scan_location', datatypes)
    schema.add_table_group('scan', '/type/scan_record', datatypes)

    schema.add_table_group('work', '/type/work', datatypes) 
    schema.add_table_group('publisher', '/type/publisher', datatypes)
    schema.add_table_group('subject', '/type/subject', datatypes)
    
    schema.add_seq('/type/edition', '/books/OL%dM')
    schema.add_seq('/type/author', '/authors/OL%dA')
    
    schema.add_seq('/type/work', '/works/OL%dW')
    schema.add_seq('/type/publisher', '/publishers/OL%dP')
    
    _sql = schema.sql
    
    # custom postgres functions required by OL.
    more_sql = """
    CREATE OR REPLACE FUNCTION get_olid(text) RETURNS text AS $$
        select regexp_replace($1, '.*(OL[0-9]+[A-Z])', E'\\1') where $1 ~ '^/.*/OL[0-9]+[A-Z]$';
    $$ LANGUAGE SQL IMMUTABLE;
    
    CREATE INDEX thing_olid_idx ON thing(get_olid(key));
    """
        
    # monkey patch schema.sql to include the custom functions
    schema.sql = lambda: web.safestr(_sql()) + more_sql    
    return schema
    
def register_schema():
    """Register the schema definied in this module as the default schema."""
    dbstore.default_schema = get_schema()

if __name__ == "__main__":
    print get_schema().sql()
