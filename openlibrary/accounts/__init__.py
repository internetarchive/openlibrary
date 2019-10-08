from .model import * #XXX: Fix this. Import only specific names

import web
from infogami.infobase.client import ClientException

## Unconfirmed functions (I'm not sure that these should be here)
def get_group(name):
    """
    Returns the group named 'name'.
    """
    return web.ctx.site.get("/usergroup/%s"%name)


def run_as(username, action, kwargs=None):
    """Escalates privileges to become username, performs action as user,
    and then de-escalates to original user.

    :param str username: Username e.g. /people/mekBot of user to run action as
    :param function action: lambda to execute under username
    :param dict kwargs: a dictionary of kwargs to send to action
    :return: Any result of the action function
    """
    # Save token of currently logged in user (or no-user)
    account = get_current_user()
    auth_token = account and account.generate_login_code()
    try:
        # Temporarily become user
        tmp_account = find(username=username)
        web.ctx.conn.set_auth_token(tmp_account.generate_login_code())
        kwargs = kwargs or {}
        resp = action(**kwargs)
    except Exception as e:
        web.ctx.conn.set_auth_token(auth_token)
        raise e

    # Return auth token to original user or no-user
    web.ctx.conn.set_auth_token(auth_token)
    return resp

## Confirmed functions (these have to be here)
def get_current_user():
    """
    Returns the currently logged in user. None if not logged in.
    """
    return web.ctx.site.get_user()


def username_available(cls, username):
    """Returns True if an OL username is available, or False otherwise"""
    return bool(
        accounts.find(username=username) or
        accounts.find(lusername=username))


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
        # the email stored in account doc is case-sensitive.
        # The lowercase of email is used in the account-email document.
        # querying that first and taking the username from there to make
        # the email search case-insensitive.
        #
        # There are accounts with case-variation of emails. To handle those,
        # searching with the original case and using lower case if that fails.
        email_doc = web.ctx.site.store.get("account-email/" + email) or web.ctx.site.store.get("account-email/" + email.lower())
        doc = email_doc and web.ctx.site.store.get("account/" + email_doc['username'])
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


def get_link(code):
    docs = web.ctx.site.store.values(type="account-link", name="code", value=code)
    if docs:
        doc = docs[0]
        return Link(doc)
    else:
        return False
