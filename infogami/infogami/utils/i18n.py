"""
Support for Internationalization.
"""
import web
import os.path
import glob

import delegate

_strings = None
_keys = None

def get_strings():
    """Returns i18n strings. strings loaded lazily."""
    if _strings is None:
        load_all()
    return _strings
    
def get_keys():
    if _keys is None:
        load_all()
    return _keys
    
def load_all():
    global _strings, _keys
    _keys, _strings = load_strings()
    run_hooks()

# hooks for initializing i18n
i18n_hooks = []

def run_hooks():
    for hook in i18n_hooks:
        hook()

def load_strings():
    """Load i18n/strings.xx files from every plugin."""
    strings = {}
    strings['nolang'] = {}
    
    keys = {}

    for plugin in delegate.plugins:
        name = os.path.basename(plugin)
        data = load_plugin(plugin)
        for lang, xstrings in data.iteritems():
            strings.setdefault(lang, {}).update(xstrings)
            keys.setdefault(name, set()).update(xstrings.keys())
    
    return keys, strings

def load_plugin(plugin):
    """Load string.xx files from plugin/i18n/string.* files."""
    path = os.path.join(plugin, "i18n", "strings.*")

    strings = {}
    
    for p in glob.glob(path):
        try:
            _, extn = os.path.splitext(p)
            lang = extn[1:] # strip dot
            strings[lang] = _read_strings(p)
        except:
            print >> web.debug, "failed to load strings from", p    

    return strings
    
def _read_strings(path):
    env = {}
    execfile(path, env)
    # __builtins__ gets added by execfile
    del env['__builtins__']
    return env

class i18n:
    """Dictionary like object to return strings in appropriate language based
    on HTTP_ACCEPT_LANGUAGE header in the request."""

    def __init__(self, default_lang="en"):
        self.default_lang = default_lang

    def __getattr__(self, key):
        return i18n_string(key, self.default_lang)

    __getitem__ = __getattr__

class i18n_string(object):
    """Lazy i18n string."""
    def __init__(self, key, default_lang="en"):
        self.key = key
        self.default_lang = default_lang

    def _get_languages(self):
        """Returns languages from HTTP_ACCEPT_LANGUAGE header of the request."""
        accept_language = web.ctx.env.get('HTTP_ACCEPT_LANGUAGE', '')

        re_accept_language = web.re_compile(', *')
        tokens = re_accept_language.split(accept_language)

        # take just the language part. ignore other details.
        # for example `en-gb;q=0.8` will be treated just as `en`.
        return [t[:2] for t in tokens] 

    def _setup(self):
        """Adds lang to web.ctx"""
        if "lang" in web.ctx:
            return

        languages = self._get_languages()

        for lang in languages:
            if lang in get_strings():
                web.ctx.lang = lang
                break
        else:
            web.ctx.lang = "nolang"

    def get(self, lang, key):
        strings = get_strings()
        if lang not in strings:
            return None
        return strings[lang].get(key, None)
        
    def __call__(self, *a): 
        return str(self) % a

    def __str__(self):
        self._setup()
        value = self.get(web.ctx.lang, self.key)

        if value is None:
            value = self.get(self.default_lang, self.key)

        if value is None:
            value = self.key

        return value

