from .model import * #XXX: Fix this. Import only specific names

import web

## Unconfirmed functions (I'm not sure that these should be here)
def get_group(name):
    """
    Returns the group named 'name'.
    """
    return web.ctx.site.get("/usergroup/%s"%name)


## Confirmed functions (these have to be here)
def get_current_user():
    """
    Returns the currently logged in user. None if not logged in.
    """
    return web.ctx.site.get_user()


def find(username=None, lusername=None, email=None):
    """Finds an account by username, email or lowercase username.
    """
    def query(name, value):
        try:
            return web.ctx.site.store.values(type="account", name=name, value=value, limit=1)[0]
        except IndexError:
            return None
    
    if username:
        doc = web.ctx.site.store.get("account/" + username)
    elif lusername:
        doc = query("lusername", lusername)
    elif email:
        doc = query("email", email)
    else:
        doc = None
        
    return doc and Account(doc)

def register(username, email, password, displayname):
    web.ctx.site.register(username = username,
                          email = email,
                          password = password,
                          displayname = displayname)


def login(username, password):
    web.ctx.site.login(username, password)

def update_account(username, **kargs):
    web.ctx.site.update_account(username, **kargs)

def check_reset_code(username, code):
    web.ctx.site.check_reset_code(username, code)

