"""utils for admin application.
"""
import web

from infogami.utils import delegate, features
from infogami.utils.view import render_template

def admin_processor(handler):
    """web.py application processor for enabling infogami and verifying admin permissions.
    """
    delegate.initialize_context()
    delegate.context.features = []
    features.loadhook()
    
    # required to give a special look and feel in site template
    delegate.context.setdefault('bodyid', 'admin')
    delegate.context.setdefault('usergroup', 'admin')

    page = handler()
    return render_template("site", page)
    
def notfound():
    msg = render_template(
            "site", 
            render_template("notfound", web.ctx.path, create=False))
    return web.notfound(msg)