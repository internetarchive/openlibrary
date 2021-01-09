from __future__ import print_function
import web
import os

import babel
from babel._compat import BytesIO
from babel.support import Translations
from babel.messages import Catalog
from babel.messages.pofile import read_po, write_po
from babel.messages.mofile import write_mo
from babel.messages.extract import extract_from_file, extract_from_dir, extract_python

root = os.path.dirname(__file__)

OL_SUPPORTED_LANGAGES = ['en', 'cs', 'de', 'es', 'fr', 'te']

def _compile_translation(po, mo):
    try:
        catalog = read_po(open(po, 'rb'))

        f = open(mo, 'wb')
        write_mo(f, catalog)
        f.close()
        print('compiled', po, file=web.debug)
    except Exception as e:
        print('failed to compile', po, file=web.debug)
        raise e

def get_locales():
    return [d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))]

def extract_templetor(fileobj, keywords, comment_tags, options):
    """Extract i18n messages from web.py templates."""
    try:
        instring = fileobj.read().decode('utf-8')
        # Replace/remove inline js '\$' which interferes with the Babel python parser:
        cleaned_string = instring.replace('\$', '')
        code = web.template.Template.generate_code(cleaned_string, fileobj.name)
        f = BytesIO(code.encode('utf-8')) # Babel wants bytes, not strings
    except Exception as e:
        print('Failed to extract ' + fileobj.name + ':', repr(e), file=web.debug)
        return []
    return extract_python(f, keywords, comment_tags, options)

def extract_messages(dirs):
    catalog = Catalog(
        project='Open Library',
        copyright_holder='Internet Archive'
    )
    METHODS = [
        ("**.py", "python"),
        ("**.html", "openlibrary.i18n:extract_templetor")
    ]
    COMMENT_TAGS = ["NOTE:"]

    for d in dirs:
        if '.html' in d:
            extracted = [(d,) + extract for extract in extract_from_file("openlibrary.i18n:extract_templetor", d)]
        else:
            extracted = extract_from_dir(d, METHODS, comment_tags=COMMENT_TAGS, strip_comment_tags=True)
        for filename, lineno, message, comments, context in extracted:
            catalog.add(message, None, [(filename, lineno)], auto_comments=comments)

    path = os.path.join(root, 'messages.pot')
    f = open(path, 'wb')
    write_po(f, catalog)
    f.close()

    print('wrote template to', path)

def compile_translations():
    for locale in get_locales():
        po_path = os.path.join(root, locale, 'messages.po')
        mo_path = os.path.join(root, locale, 'messages.mo')

        if os.path.exists(po_path):
            _compile_translation(po_path, mo_path)

def update_translations():
    pot_path = os.path.join(root, 'messages.pot')
    template = read_po(open(pot_path, 'rb'))

    for locale in get_locales():
        po_path = os.path.join(root, locale, 'messages.po')
        mo_path = os.path.join(root, locale, 'messages.mo')

        if os.path.exists(po_path):
            catalog = read_po(open(po_path, 'rb'))
            catalog.update(template)

            f = open(po_path, 'wb')
            write_po(f, catalog)
            f.close()
            print('updated', po_path)

    compile_translations()

@web.memoize
def load_translations(lang):
    po = os.path.join(root, lang, 'messages.po')
    mo_path = os.path.join(root, lang, 'messages.mo')

    if os.path.exists(mo_path):
        return Translations(open(mo_path, 'rb'))


def get_ol_locale():
    """
    Gets the locale from the cookie and -if not found- sets it to the
    highest priority language of the Accept-Language header, that's also part
    of the Open Library supported languages.
    """
    locale_cookie = web.cookies().get('i18n_code')
    if locale_cookie is not None:
        ol_locale = locale_cookie
    else:
        browser_accepted_langs = web.ctx.env.get('HTTP_ACCEPT_LANGUAGE')
        if browser_accepted_langs:
            # Parse the accepted language header string into a list
            languages = browser_accepted_langs.split(',')
            # Remove the quality-value weights and keep only the locales
            accepted_langs = [lang.partition(';')[0] for lang in languages]
            # The default locale is 'en' unless we support a browser-suggested language
            ol_locale = 'en'
            for lang in accepted_langs:
                if lang in OL_SUPPORTED_LANGAGES:
                    ol_locale = lang
                    break
        else:
            ol_locale = 'en'
        web.setcookie('i18n_code', ol_locale, secure=False)
    return ol_locale

@web.memoize
def load_locale(lang):
    try:
        return babel.Locale(lang)
    except babel.UnknownLocaleError:
        pass

class GetText:
    def __call__(self, string, *args, **kwargs):
        """Translate a given string to the language of the current locale."""
        website_locale = get_ol_locale()
        translations = load_translations(website_locale)
        value = (translations and translations.ugettext(string)) or string

        if args:
            value = value % args
        elif kwargs:
            value = value % kwargs

        return value

    def __getattr__(self, key):
        from infogami.utils.i18n import strings
        # for backward-compatability
        return strings.get('', key)

class LazyGetText:
    def __call__(self, string, *args, **kwargs):
        """Translate a given string lazily."""
        return LazyObject(lambda: GetText()(string, *args, **kwargs))

class LazyObject:
    def __init__(self, creator):
        self._creator = creator

    def __str__(self):
        return web.safestr(self._creator())

    def __repr__(self):
        return repr(self._creator())

    def __add__(self, other):
        return self._creator() + other

    def __radd__(self, other):
        return other + self._creator()


def ungettext(s1, s2, _n, *a, **kw):
    website_locale = get_ol_locale()
    translations = load_translations(website_locale)
    value = translations and translations.ungettext(s1, s2, _n)
    if not value:
        # fallback when translation is not provided
        if _n == 1:
            value = s1
        else:
            value = s2

    if a:
        return value % a
    elif kw:
        return value % kw
    else:
        return value

def gettext_territory(code):
    """Returns the territory name in the current locale."""
    lang = get_ol_locale()
    locale = load_translations(lang)
    return locale.territories.get(code, code)

gettext = GetText()
ugettext = gettext
lgettext = LazyGetText()
_ = gettext
