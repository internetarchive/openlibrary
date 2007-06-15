"""
db schema for review plugin.
"""
import web
from infogami.utils import dbsetup

schema = """
CREATE TABLE review (
  id serial primary key,
  site_id int references site,
  page_id int references page,
  user_id int references login,
  revision int default 0,
  unique (site_id, page_id, user_id)
);
"""

upgrade = dbsetup.module('review', schema).upgrade
