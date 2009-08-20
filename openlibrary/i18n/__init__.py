"""i18n support for Open Library using GNU gettext. Python module
babel is used to manage the message catalogs.

## Introduction

To add i18n support to Open Library, templates and macros are modified
to use gettext function calls. For brevity, the gettext function is
abbreviated as _.

    <a href="..">$_("More search options")</a>

The messages in the the templates and macros are extracted and .pot file is created.

    $ ./script/extract-messages
    created openlibrary/i18n/messages.pot
    $ cat openlibrary/i18n/messages.pot
    ...
    #: templates/site.html:29
    msgid "Open Library"
    msgstr ""

    #: templates/site.html:52
    msgid "Search"
    msgstr ""
    ...
    
The .pot file contains msgid and msgstr for each translation used.
The `msgstr` field for each entry is filled with the translation of
the required language and that file is placed at
openlibrary/i18n/$locale/messages.po.

    $ mkdir openlibrary/i18n/te
    $ cp openlibrary/i18n/messages.pot openlibrary/i18n/te/messages.po
    $ # edit openlibrary/i18n/te/messages.po and fill the translations

The .po files needs to be compiled to .mo files to be able to use them
by gettext system. That is achieved by running
./script/compile-translations script.
    
    $ ./scripts/compile-translations
    compiling openlibrary/i18n/te/messages.po
    compiling openlibrary/i18n/it/messages.po
    ...

## Glossory

.po - portable object
.pot - portable object template
.mo - machine object
"""

import web
import os

from babel.support import Translations
from babel.messages.pofile import read_po
from babel.messages.mofile import write_mo


root = os.path.dirname(__file__)

def i18n_processor(self):
    pass
    
def _compile_translation(po, mo):
    try:
        catalog = read_po(open(po))
        
        f = open(mo, 'wb')
        write_mo(f, catalog)
        f.close()
        print >> web.debug, 'compiled', po
    except:
        print >> web.debug, 'failed to compile', po

def get_locales():
    return [d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))]

def compile_translations():
    for locale in get_locales():
        po_path = os.path.join(root, locale, 'messages.po')
        mo_path = os.path.join(root, locale, 'messages.mo')

        if os.path.exists(po_path):
            _compile_translation(po_path, mo_path)

def update_translations():
    for locale in get_locales():
        pass
    
@web.memoize
def load_translations(lang):
    po = os.path.join(root, lang, 'messages.po')
    mo_path = os.path.join(root, lang, 'messages.mo')
    
    if os.path.exists(mo_path):
        return Translations(open(mo_path))

class GetText:
    def __call__(self, string, *a, **kw):
        """Translate a given string to the language of the current locale."""
        translations = load_translations(web.ctx.lang)
        value = (translations and translations.ugettext(string)) or string
        
        if a:
            value = value % a
        elif kw:
            value = value % kw
        
        return value
        
    def __getattr__(self, key):
        from infogami.utils.i18n import strings
        # for backward-compatability
        return strings.get('', key)
    
gettext = GetText()
_ = gettext
