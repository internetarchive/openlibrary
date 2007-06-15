"""
upgrade for moving templates to wiki.
"""
import infogami
from infogami.utils import dbsetup
from infogami.core import db
from infogami import config

import web
import os

upgrade = dbsetup.module('wikitemplates', None).upgrade

def add_template(title, path, dbpath):
    root = os.path.dirname(infogami.__file__)
    body = open(root + "/" + path).read()
    db.new_version(config.site, dbpath, None, 
        web.storage(title=title, template="template", body=body))

@upgrade
def add_wikitemplates():
    web.ctx.ip = ""
    #add_template("View Template", "core/templates/view.html", "templates/page/view.tmpl")
    #add_template("Edit Template", "core/templates/edit.html", "templates/page/edit.tmpl")
    #add_template("Site Template", "core/templates/site.html", "templates/site.tmpl")
