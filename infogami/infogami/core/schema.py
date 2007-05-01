"""
db schema for infogami core.
"""

import web
from infogami.utils import dbsetup

schema = """
CREATE TABLE site (
  id serial primary key,
  url text
);

CREATE TABLE page (
  id serial primary key,
  site_id int references site,
  path text
);

CREATE TABLE version (
  id serial primary key,
  page_id int references page,
  author text,
  created timestamp default (current_timestamp at time zone 'utc')
);

CREATE TABLE datum (
  id serial primary key,
  version_id int references version,
  key text,
  value text
);
"""

upgrade = dbsetup.module("core", schema).upgrade

@upgrade
def add_login_table():
    """add login table"""
    web.query("""
        CREATE TABLE login (
          id serial primary key,
          name text unique,
          email text,
          password text
        )""")

def initialize_revisions():
    pages = web.query("SELECT * FROM page")

    for p in pages:
        page_id = p.id
        versions = web.query("SELECT * FROM version WHERE page_id=$page_id ORDER BY id", vars=locals())
        for i, v in enumerate(versions):
            id = v.id
            web.update('version', where='id=$id', revision=i+1, vars=locals())

@upgrade
def add_version_revision():
    """revision column is added to version table."""
    web.query("ALTER TABLE version ADD COLUMN revision int")
    web.query("ALTER TABLE version ALTER COLUMN revision SET DEFAULT 0")
    initialize_revisions()

@upgrade
def bad_revision_bug():
    """bug fix in initializing revisions"""
    initialize_revisions()

@upgrade
def author_ipaddress():
    """author_id and ip_address instead of author in version table."""
    versions = list(web.query('SELECT id, author FROM version'))
    web.query('ALTER TABLE version DROP COLUMN author')
    web.query('ALTER TABLE version ADD COLUMN author_id int references login')
    web.query('ALTER TABLE version ADD COLUMN ip_address text')
    
    for v in versions:
        if not v.author:
            continue

        if v.author[0] in '0123456789':
            author_id = None
            ip_address = v.author
        else:
            name = v.author
            d = web.query('SELECT id FROM login WHERE name=$name', vars=locals())
            author_id = (d and d[0].id) or None
            ip_address = None
                
        id = v.id
        web.update('version', where='id=$id', author_id=author_id, ip_address=ip_address, vars=locals())

@upgrade
def page_template():
    """add template for every version."""
    versions = web.query('SELECT id FROM version')
    for v in versions:
        web.insert('datum', version_id=v.id, key='template', value='page')
