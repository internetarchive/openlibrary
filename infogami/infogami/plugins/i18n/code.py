"""
i18n: allow keeping i18n strings in wiki
"""

import web
from infogami.utils import delegate, i18n
from infogami.utils.view import public
from infogami.plugins.wikitemplates.code import register_wiki_template
from infogami import config
from infogami import tdb
import infogami
import db
import os.path

re_i18n = web.re_compile(r'^i18n/strings\.(.*)$')

class hook(tdb.hook):
    def on_new_version(self, page):
        """Update i18n strings when a i18n wiki page is changed."""
        if page.type.name == 'i18n':
            path = page.name
            result = re_i18n.match(path)
            if result:
                lang = result.group(1)
                update_strings(lang, page.d)

def get_site():
    from infogami.core import db
    return db.get_site(config.site)

def load_strings():
    """Load strings from wiki."""
    # This function is called from the first request that uses i18n
    pages = db.get_all_strings(get_site())
    for page in pages:
        result = re_i18n.match(page.name)
        if result:
            lang = result.group(1)
            update_strings(lang, page.d)

i18n.i18n_hooks.append(load_strings)

def update_strings(lang, data):
    #@@ every site should have different strings
    strings = i18n.get_strings()
    items = [(key.split('.', 1)[1], value) for key, value in data.iteritems() if '.' in key and value.strip() != '']
    strings[lang] = dict(items)

# register i18n templates
register_wiki_template("i18n View Template", 
                       "plugins/i18n/templates/view.html",
                       "templates/i18n/view.tmpl")

register_wiki_template("i18n edit Template", 
                       "plugins/i18n/templates/edit.html",
                       "templates/i18n/edit.tmpl")

@infogami.install_hook
@infogami.action
def movestrings():
    """Moves i18n strings to wiki."""
    from infogami.core import db
    web.load()
    web.ctx.ip=""
    
    strings = {}
    
    for p in delegate.plugins:
        name = os.path.basename(p)
        data = i18n.load_plugin(p)
        for lang, d in data.iteritems():
            if lang not in strings:
                strings[lang] = {}
            for key, value in d.iteritems():
                strings[lang][name + '.' + key] = value
                
    type = db.get_type('i18n', create=True)
    for lang, d in strings.iteritems():
        wikipath = "i18n/strings." + lang
        db.new_version(get_site(), wikipath, type, d).save()

@public
def get_i18n_keys(plugin):
    keys = i18n.get_keys()
    return keys.get(plugin, {})

