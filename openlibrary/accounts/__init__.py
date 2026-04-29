import datetime
from typing import TYPE_CHECKING

import web

from infogami.utils.view import public
from openlibrary.utils.request_context import site

# FIXME: several modules import things from accounts.model
# directly through openlibrary.accounts
from .model import *  # noqa: F403
from .model import Account, Link

if TYPE_CHECKING:
    from openlibrary.plugins.upstream.models import User


# Unconfirmed functions (I'm not sure that these should be here)
def get_group(name):
    """
    Returns the group named 'name'.
    """
    return web.ctx.site.get(f"/usergroup/{name}")


class RunAs:
    """
    Escalates privileges to become username, performs action as user,
    and then de-escalates to original user.
    """

    def __init__(self, username: str) -> None:
        """
        :param str username: Username e.g. /people/mekBot of user to run action as
        """
        self.tmp_account = find(username=username)
        self.calling_user_auth_token = None

        if not self.tmp_account:
            raise KeyError("Invalid username")

    def __enter__(self):
        # Save token of currently logged in user (or no-user)
        account = get_current_user()
        self.calling_user_auth_token = account and account.generate_login_code()

        # Temporarily become user
        web.ctx.conn.set_auth_token(self.tmp_account.generate_login_code())
        return self.tmp_account

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Return auth token to original user or no-user
        web.ctx.conn.set_auth_token(self.calling_user_auth_token)


# Confirmed functions (these have to be here)
@public
def get_current_user() -> "User | None":
    """
    Returns the currently logged in user. None if not logged in.
    """
    return site.get().get_user()


@public
def get_days_registered(user) -> str:
    """Return a Matomo custom dimension value for patron account age.

    Buckets for visit-scoped dimension 1 ("Days Since Registration"):
      visitor  — not logged in
      d0       — account created today (UTC)
      d1+      — 1-6 days since registration
      d7+      — 7-13 days
      d14+     — 14-29 days
      d30+     — 30-89 days
      d90+     — 90+ days (also the safe fallback on any error)
    """
    if not user:
        return "visitor"
    try:
        reg_date = user.created.date()
        days = (datetime.datetime.now(datetime.UTC).date() - reg_date).days
    except (AttributeError, TypeError):
        # If the date is incorrectly encoded, assume the patron
        # registered a long time ago before we had this set up.
        return "d90+"
    if days <= 0:
        return "d0"
    elif days < 7:
        return "d1+"
    elif days < 14:
        return "d7+"
    elif days < 30:
        return "d14+"
    elif days < 90:
        return "d30+"
    return "d90+"


def find(username: str | None = None, lusername: str | None = None, email: str | None = None) -> Account | None:
    """Finds an account by username, email or lowercase username."""

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
        doc = email_doc and web.ctx.site.store.get("account/" + email_doc["username"])
    else:
        doc = None

    return doc and Account(doc)


def register(username, email, password, displayname):
    web.ctx.site.register(username=username, email=email, password=password, displayname=displayname)


def login(username, password):
    web.ctx.site.login(username, password)


def update_account(username, **kargs):
    web.ctx.site.update_account(username, **kargs)


def get_link(code: str) -> Link | bool:
    docs = web.ctx.site.store.values(type="account-link", name="code", value=code)
    if docs:
        doc = docs[0]
        return Link(doc)
    else:
        return False
