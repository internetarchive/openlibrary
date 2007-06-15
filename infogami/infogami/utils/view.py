from infogami.utils import markdown
from context import context
import web
import os
from infogami import config
from infogami.utils.i18n import i18n


wiki_processors = []
def register_wiki_processor(p):
    wiki_processors.append(p)

def get_markdown(text):
    import macro
    md = markdown.Markdown(source=text, safe_mode=False)
    md = macro.macromarkdown(md)
    md.postprocessors += wiki_processors
    return md

def get_doc(text):
    return get_markdown(text)._transform()

web.template.Template.globals.update(dict(
  changequery = web.changequery,
  datestr = web.datestr,
  numify = web.numify,
  ctx = context,
  _ = i18n(),
))

render = web.storage()

def public(f):
    """Exposes a funtion in templates."""
    web.template.Template.globals[f.__name__] = f
    return f

@public
def format(text): 
    return str(get_markdown(text))

@public
def link(path, text=None):
    return '<a href="%s">%s</a>' % (web.ctx.homepath + path, text or path)

@public
def url(path):
    if path.startswith('/'):
        return web.ctx.homepath + path
    else:
        return path

@public
def homepath():
    return web.ctx.homepath        

@public
def add_stylesheet(path):
    context.stylesheets.append(url(path))
    return ""
    
@public
def add_javascript(path):
    context.javascripts.append(url(path))
    return ""

@public
def spacesafe(text):
    text = web.websafe(text)
    text = text.replace(' ', '&nbsp;');
    return text
    
def set_error(msg):
    context.error = msg

def load_templates(dir):
    cache = getattr(config, 'cache_templates', True)

    path = dir + "/templates/"
    if os.path.exists(path):
        name = os.path.basename(dir)
        render[name] = web.template.render(path, cache=cache)

def render_site(url, page):
    return render.core.site(page)

def get_static_resource(path):
    rx = web.re_compile(r'^files/([^/]*)/(.*)$')
    result = rx.match(path)
    if not result:
        return web.notfound()

    plugin, path = result.groups()

    # this distinction will go away when core is also treated like a plugin.
    if plugin == 'core':
        fullpath = "infogami/core/files/%s" % (path)
    else:
        fullpath = "infogami/plugins/%s/files/%s" % (plugin, path)

    if not os.path.exists(fullpath):
        return web.notfound()
    else:
        return open(fullpath).read()
    
