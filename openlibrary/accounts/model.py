"""

"""
import time
import datetime
import hmac
import random
import simplejson
import uuid
import urllib
import urllib2

import lepl.apps.rfc3696
import web

from infogami import config
from infogami.utils.view import render_template
from infogami.infobase.client import ClientException
from openlibrary.core import lending, helpers as h


def valid_email(email):
    return lepl.apps.rfc3696.Email()(email)

def sendmail(to, msg, cc=None):
    cc = cc or []
    if config.get('dummy_sendmail'):
        message = ('' +
            'To: ' + to + '\n' +
            'From:' + config.from_address + '\n' +
            'Subject:' + msg.subject + '\n' +
            '\n' +
            web.safestr(msg))

        print >> web.debug, "sending email", message
    else:
        web.sendmail(config.from_address, to, subject=msg.subject.strip(),
                     message=web.safestr(msg), cc=cc)

def verify_hash(secret_key, text, hash):
    """Verifies if the hash is generated
    """
    salt = hash.split('$', 1)[0]
    return generate_hash(secret_key, text, salt) == hash

def generate_hash(secret_key, text, salt=None):
    salt = salt or hmac.HMAC(secret_key, str(random.random())).hexdigest()[:5]
    hash = hmac.HMAC(secret_key, salt + web.utf8(text)).hexdigest()
    return '%s$%s' % (salt, hash)

def get_secret_key():
    return config.infobase['secret_key']

def generate_uuid():
    return str(uuid.uuid4()).replace("-", "")

def send_verification_email(username, email):
    """Sends account verification email.
    """
    key = "account/%s/verify" % username

    doc = create_link_doc(key, username, email)
    web.ctx.site.store[key] = doc

    link = web.ctx.home + "/account/verify/" + doc['code']
    msg = render_template("email/account/verify", username=username, email=email, password=None, link=link)
    sendmail(email, msg)

def create_link_doc(key, username, email):
    """Creates doc required for generating verification link email.

    The doc contains username, email and a generated code.
    """
    code = generate_uuid()

    now = datetime.datetime.utcnow()
    expires = now + datetime.timedelta(days=14)

    return {
        "_key": key,
        "_rev": None,
        "type": "account-link",
        "username": username,
        "email": email,
        "code": code,
        "created_on": now.isoformat(),
        "expires_on": expires.isoformat()
    }



class Link(web.storage):
    def get_expiration_time(self):
        d = self['expires_on'].split(".")[0]
        return datetime.datetime.strptime(d, "%Y-%m-%dT%H:%M:%S")

    def get_creation_time(self):
        d = self['created_on'].split(".")[0]
        return datetime.datetime.strptime(d, "%Y-%m-%dT%H:%M:%S")

    def delete(self):
        del web.ctx.site.store[self['_key']]



class Account(web.storage):
    @property
    def username(self):
        return self._key.split("/")[-1]

    def get_edit_count(self):
        user = self.get_user()
        return user and user.get_edit_count() or 0

    @property
    def registered_on(self):
        """Returns the registration time."""
        t = self.get("created_on")
        return t and h.parse_datetime(t)

    @property
    def activated_on(self):
        user = self.get_user()
        return user and user.created

    @property
    def displayname(self):
        key = "/people/" + self.username
        doc = web.ctx.site.get(key)
        if doc:
            return doc.displayname or self.username
        elif "data" in self:
            return self.data.get("displayname") or self.username
        else:
            return self.username

    def creation_time(self):
        d = self['created_on'].split(".")[0]
        return datetime.datetime.strptime(d, "%Y-%m-%dT%H:%M:%S")

    def get_recentchanges(self, limit=100, offset=0):
        q = dict(author=self.get_user().key, limit=limit, offset=offset)
        return web.ctx.site.recentchanges(q)

    def verify_password(self, password):
        return verify_hash(get_secret_key(), password, self.enc_password)

    def update_password(self, new_password):
        web.ctx.site.update_account(self.username, password=new_password)

    def update_email(self, email):
        web.ctx.site.update_account(self.username, email=email)

    def send_verification_email(self):
        send_verification_email(self.username, self.email)

    def activate(self):
        web.ctx.site.activate_account(username=self.username)

    def block(self):
        """Blocks this account."""
        web.ctx.site.update_account(self.username, status="blocked")

    def unblock(self):
        """Unblocks this account."""
        web.ctx.site.update_account(self.username, status="active")

    def is_blocked(self):
        """Tests if this account is blocked."""
        return self.status == "blocked"

    def login(self, password):
        """Tries to login with the given password and returns the status.

        The return value can be one of the following:

            * ok
            * account_not_vefified
            * account_not_found
            * account_incorrect_password
            * account_blocked

        If the login is successful, the `last_login` time is updated.
        """
        if self.is_blocked():
            return "account_blocked"
        try:
            web.ctx.site.login(self.username, password)
        except ClientException, e:
            code = e.get_data().get("code")
            return code
        else:

            # XXX we need to check if IA and OL accounts linked
            # and create accounts which don't exist

            self['last_login'] = datetime.datetime.utcnow().isoformat()
            self._save()
            return "ok"

    def generate_login_code(self):
        """Returns a string that can be set as login cookie to log in as this user.
        """
        user_key = "/people/" + self.username
        t = datetime.datetime(*time.gmtime()[:6]).isoformat()
        text = "%s,%s" % (user_key, t)
        return text + "," + generate_hash(get_secret_key(), text)

    def _save(self):
        """Saves this account in store.
        """
        web.ctx.site.store[self._key] = self

    @property
    def last_login(self):
        """Returns the last_login time of the user, if available.

        The `last_login` will not be available for accounts, who haven't
        been logged in after this feature is added.
        """
        t = self.get("last_login")
        return t and h.parse_datetime(t)

    def get_user(self):
        key = "/people/" + self.username
        doc = web.ctx.site.get(key)
        return doc

    def get_creation_info(self):
        key = "/people/" + self.username
        doc = web.ctx.site.get(key)
        return doc.get_creation_info()

    def get_activation_link(self):
        key = "account/%s/verify"%self.username
        doc = web.ctx.site.store.get(key)
        if doc:
            return Link(doc)
        else:
            return False

    def get_password_reset_link(self):
        key = "account/%s/password"%self.username
        doc = web.ctx.site.store.get(key)
        if doc:
            return Link(doc)
        else:
            return False

    def get_links(self):
        """Returns all the verification links present in the database.
        """
        return web.ctx.site.store.values(type="account-link", name="username",
                                         value=self.username)

    def get_tags(self):
        """Returns list of tags that this user has.
        """
        return self.get("tags", [])

    def has_tag(self, tag):
        return tag in self.get_tags()

    def add_tag(self, tag):
        tags = self.get_tags()
        if tag not in tags:
            tags.append(tag)
        self['tags'] = tags
        self._save()

    def remove_tag(self, tag):
        tags = self.get_tags()
        if tag in tags:
            tags.remove(tag)
        self['tags'] = tags
        self._save()

    def set_bot_flag(self, flag):
        """Enables/disables the bot flag.
        """
        self.bot = flag
        self._save()

    @property
    def itemname(self):
        """Retrieves the Archive.org itemname which links Open Library and
        Internet Archive accounts
        """
        return getattr(self, 'archive_user_itemname', None)

    def get_linked_ia_account(self):
        link = self.itemname
        return InternetArchiveAccount.get(itemname=link) if link else None

class OpenLibraryAccount(Account):

    def authenticates(self, password):
        return self.authenticate(self.email, password) == "ok"

    @classmethod
    def create(cls, username, email, password, test=False):
        if test:
            return cls(email="test@openlibrary.org", itemname="test",
                       screenname="test")
        if cls.get(email=email):
            raise ValueError('email_registered')
        if cls.get(username=username):
            raise ValueError('username_registered')

        # XXX Create account here
        return True

    @classmethod
    def get(cls, link=None, email=None, username=None,  test=False):
        """Attempts to retrieve an openlibrary account by its email or
        archive.org itemname (i.e. link)"""
        if link:
            return cls.get_by_link(link, test=test)
        elif email:
            return cls.get_by_email(email, test=test)
        elif username:
            return cls.get_by_username(username, test=test)
        raise ValueError("Open Library email or Archive.org itemname required.")

    @classmethod
    def get_by_username(cls, username, test=False):
        return accounts.find(lusername=username.lower())

    @classmethod
    def get_by_link(cls, link, test=False):
        ol_accounts = web.ctx.site.store.values(
            type="account", name="archive_user_itemname", value=email)
        return OpenLibraryAccount(**ol_accounts[0]) if ol_accounts else None

    @classmethod
    def get_by_email(cls, email, test=False):
        """the email stored in account doc is case-sensitive.
        The lowercase of email is used in the account-email document.
        querying that first and taking the username from there to make
        the email search case-insensitive.

        There are accounts with case-variation of emails. To handle
        those, searching with the original case and using lower case
        if that fails.
        """
        email_doc = (web.ctx.site.store.get("account-email/" + email) or
                     web.ctx.site.store.get("account-email/" + email.lower()))
        if email_doc and 'username' in email_doc:
            doc = web.ctx.site.store.get("account/" + email_doc['username'])
            return OpenLibraryAccount(**doc) if doc else None
        return None


class InternetArchiveAccount(object):

    def __init__(self, **kwargs):
        for k in kwargs:
            setattr(self, k, kwargs[k])

    def authenticates(self, password):
        return self.authenticate(self.username, password) == "ok"

    @classmethod
    def create(cls, screenname, email, password, test=False):
        if test:
            return cls(email="test@archive.org", itemname="test",
                       screenname="test")
        if cls.get(email=email):
            raise ValueError('email_registered')
        if cls.get(screenname=screenname):
            raise ValueError('screenname_registered')

        # XXX Create account here
        return True

    @classmethod
    def _post_ia_auth_api(cls, test=False, **data):
        token = lending.config_ia_ol_auth_key
        if 'token' not in data and token:
            data['token'] = token
        if test or not token:
            data['test'] = "true"
        payload = urllib.urlencode(data)
        response = simplejson.loads(urllib2.urlopen(
            lending.IA_AUTH_API_URL, payload).read())
        return response

    @classmethod
    def get(cls, screenname=None, email=None, itemname=None, test=False):
        if screenname:
            return cls.get_by_screenname(screenname, test=test)
        elif email:
            return cls.get_by_email(email, test=test)
        elif itemname:
            return cls.get_by_itemname(itemname, test=test)
        return None

    @classmethod
    def get_by_screenname(cls, screenname, test=False):
        response = cls._post_ia_auth_api(test=test, **{
            "screenname": screenname,
            "service": "getUser"
        })
        return response
        if response and response.get('account_found', False):
            return cls(**response)

    @classmethod
    def get_by_email(cls, email, test=False):
        response = cls._post_ia_auth_api(test=test, **{
            "email": email,
            "service": "getUser"
        })
        if response and response.get('account_found', False):
            return cls(**response)

    @classmethod
    def get_by_itemname(cls, itemname, test=False):
        response = cls._post_ia_auth_api(test=test, **{
            "itemname": itemname,
            "service": "getUser"
        })
        if response and response.get('account_found', False):
            return cls(**response)

    @classmethod
    def authenticate(cls, email, password, test=False):
        return cls._post_ia_auth_api(test=test, **{
            "email": email,
            "password": password,
            "service": "authUser",
        })
