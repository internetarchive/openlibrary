"""

"""
import time
import datetime
import hmac
import random
import uuid

import web

from infogami import config
from infogami.utils.view import render_template
from infogami.infobase.client import ClientException
from openlibrary.core import helpers as h
from openlibrary.core import support


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
        web.sendmail(config.from_address, to, subject=msg.subject.strip(), message=web.safestr(msg), cc=cc)

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
        
    def get_cases(self):
        """Returns all support cases filed by this user.
        """
        email = self.email
        username = self.username
        
        # XXX-Anand: very inefficient. Optimize it later.
        cases = support.Support().get_all_cases()
        cases = [c for c in cases if c.creator_email == email or c.creator_username == username]
        return cases

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
        return web.ctx.site.store.values(type="account-link", name="username", value=self.username)

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