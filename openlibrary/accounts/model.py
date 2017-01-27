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
        return getattr(self, 'status', '') == "blocked"

    def login(self, password):
        """Tries to login with the given password and returns the status.

        The return value can be one of the following:

            * ok
            * account_not_verified
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
        return getattr(self, 'internetarchive_itemname', None)

    def get_linked_ia_account(self):
        link = self.itemname
        return InternetArchiveAccount.get(itemname=link) if link else None

class OpenLibraryAccount(Account):

    @classmethod
    def create(cls, username, email, password, test=False, verify=True):
        if test:
            return cls(email="test@openlibrary.org", itemname="test",
                       screenname="test")
        if cls.get(email=email):
            raise ValueError('email_registered')
        if cls.get(username=username):
            raise ValueError('username_registered')

        raise NotImplementedError('account_creation_not_implemented')
        # XXX Create account here
        account = web.ctx.site.register(
            username=username,
            email=email,
            password=password,
            displayname=username)
        if verify:
            send_verification_email(username, email)
        return account

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
        try:
            return cls(web.ctx.site.store.values(
                type="account", name="lusername", value=username, limit=1)[0])
        except IndexError:
            return None

    @classmethod
    def get_by_link(cls, link, test=False):
        ol_accounts = web.ctx.site.store.values(
            type="account", name="internetarchive_itemname", value=link)
        return cls(ol_accounts[0]) if ol_accounts else None

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
            return cls(doc) if doc else None
        return None

    @property
    def verified(self):
        return not (getattr(self, 'status', '') == 'pending')

    @property
    def blocked(self):
        return getattr(self, 'status', '') == 'blocked'

    def unlink(self):
        _ol_account = web.ctx.site.store.get(self._key)
        _ol_account['internetarchive_itemname'] = None
        web.ctx.site.store[self._key] = _ol_account

    @classmethod
    def authenticate(cls, email, password, test=False):
        ol_account = cls.get(email=email, test=test)
        if not ol_account:
            return "account_not_found"
        if ol_account.is_blocked():
            return "account_blocked"
        try:
            web.ctx.site.login(ol_account.username, password)
        except ClientException, e:
            code = e.get_data().get("code")
            return code
        else:
            return "ok"

class InternetArchiveAccount(web.storage):

    def __init__(self, **kwargs):
        for k in kwargs:
            setattr(self, k, kwargs[k])

    @classmethod
    def create(cls, screenname, email, password, test=False):
        screenname = screenname.replace('@', '')  # remove IA @
        if test:
            return cls(email="test@archive.org", itemname="test",
                       screenname="test")
        if cls.get(email=email):
            raise ValueError('email_registered')
        if cls.get(screenname=screenname):
            raise ValueError('screenname_registered')

        raise NotImplementedError('account_creation_not_implemented')
        response = cls._post_ia_user_api(
            service='createUser', email=email, password=password,
            username=username, test=test)

    @classmethod
    def xauth(cls, **data):
        return cls._post_ia_xauth_api(**data)

    @classmethod
    def _post_ia_xauth_api(cls, test=None, **data):
        service = data.pop('service', u'')
        url = "%s?op=%s" % (lending.IA_XAUTH_API_URL, service)
        data.update({
            'client_access': lending.config_ia_ol_xauth_s3.get('s3_key'),
            'client_secret': lending.config_ia_ol_xauth_s3.get('s3_secret')
        })
        payload = urllib.urlencode(data)
        if test:
            url += "&developer=%s" % test
        try:
            response = urllib2.urlopen(url, payload).read()
        except urllib2.HTTPError as e:
            if e.code == 403:
                return {'error': e.read(), 'code': 403}
            else:
                response = e.read()
        return simplejson.loads(response)

    @classmethod
    def _post_ia_user_api(cls, test=False, **data):
        token = lending.config_ia_ol_auth_key
        if 'token' not in data and token:
            data['token'] = token
        if test or not token:  # ?
            data['test'] = "true"
        payload = urllib.urlencode(data)
        response = simplejson.loads(urllib2.urlopen(
            lending.IA_USER_API_URL, payload).read())
        return response

    @classmethod
    def get(cls, email, test=False, _json=False):
        response = cls._post_ia_xauth_api(email=email, test=test, service="info")
        if 'success' in response:
            values = response.get('values', {})
            if values:
                values['email'] = email
            return values if _json else cls(**values)

    @classmethod
    def authenticate(cls, email, password, test=False):
        return cls._post_ia_user_api(test=test, **{
            "email": email,
            "password": password,
            "service": "authUser",
        })


def audit_accounts(email, password, test=False):
    if not valid_email(email):
        return {'error': 'invalid_email'}

    audit = {
        'email': email,
        'authenticated': False,
        'has_ia': False,
        'has_ol': False,
        'link': False
    }

    ol_resp = OpenLibraryAccount.authenticate(email, password)
    ia_resp = InternetArchiveAccount.authenticate(email, password)

    # One of the accounts must authenticate w/o error
    if "ok" not in (ol_resp, ia_resp):
        for resp in (ol_resp, ia_resp):
            if resp != "account_not_found":
                return {'error': resp}
        return {'error': 'account_user_notfound'}

    ol_account = OpenLibraryAccount.get(email=email, test=test)
    ia_account = ((ol_account.get_linked_ia_account() if ol_account else None) or
                  InternetArchiveAccount.get(email=email, test=test))

    print(ia_account)

    if ia_account:
        audit['has_ia'] = ia_account.itemname
        if ia_resp == "ok":
            if ia_account.email == email:
                audit['authenticated'] = 'ia'

            # Get the OL account which links to this IA account, if
            # one exists (i.e. this IA account could be linked to an
            # OL account with a different email)
            _ol_account = OpenLibraryAccount.get(link=ia_account.itemname,
                                                 test=test)
            link = _ol_account.itemname if _ol_account else None

            if link:
                ol_account = _ol_account

            # If no linked account was found but there's an ol_account
            # having the same email as this IA account, mark them to
            # be linked
            elif not link and ol_account:
                link = ia_account.itemname

            if ol_account and link:
                if not ol_account.verified:
                    return {'error': 'ol_account_not_activated'}
                if ol_account.blocked:
                    return {'error': 'ol_account_blocked'}
                audit['link'] = link
                audit['has_ol'] = ol_account.username

                # Kludge so if a user logs in with IA credentials, we
                # can fetch the linked OL account and set an
                # auth_token even when we don't have the OL user's
                # password in order to perform web.ctx.site.login.
                # Their auth checks out via IA, set their auth_token for OL
                web.ctx.conn.set_auth_token(ol_account.generate_login_code())

    if ol_account:
        if not audit['authenticated']:
            status = ol_account.login(password)
            if status == "ok":
                audit['has_ol'] = ol_account.username
                if ol_account.email == email:
                    audit['authenticated'] = 'ol'

                # link IA account if it exists
                if ia_account:
                    if not ia_account.verified:
                        return {'error': 'ia_account_not_activate'}
                    audit['has_ia'] = ia_account.itemname
                    audit['link'] = ia_account.itemname

            else:
                return {'error': status}

        if not audit['authenticated']:
            return {'error': "invalid_ol_credentials"}

    if ia_account and not audit['authenticated']:
        return {'error': "invalid_ia_credentials"}

    # Links the accounts if they can be and are not already:
    if (audit['has_ia'] and audit['has_ol'] and
        audit['authenticated'] and not ol_account.itemname):
        audit['link'] = ia_account.itemname

        _ol_account = web.ctx.site.store.get(ol_account._key)
        _ol_account['internetarchive_itemname'] = ia_account.itemname
        web.ctx.site.store[ol_account._key] = _ol_account

    return audit


def link_accounts(email, password, bridgeEmail="", bridgePassword="",
                  username="", test=False):

    audit = audit_accounts(email, password)

    if 'error' in audit:
        return audit

    ia_account = (InternetArchiveAccount.get(
        itemname=audit['has_ia'], test=test) if
                  audit.get('has_ia', False) else None)
    ol_account = (OpenLibraryAccount.get(email=email, test=test) if
                  audit.get('has_ol', False) else None)

    if ia_account and ol_account:
        if not audit['link']:
            audit['link'] = ia_account.itemname

            # avoids Document Update conflict
            _ol_account = web.ctx.site.store.get(ol_account._key)
            _ol_account['internetarchive_itemname'] = ia_account.itemname
            web.ctx.site.store[ol_account._key] = _ol_account

        return audit
    elif not (ia_account or ol_account):
        return {'error': 'account_not_found'}
    else:
        # Link existing accounts
        if bridgeEmail and bridgePassword:
            if not valid_email(bridgeEmail):
                return {'error': 'invalid_bridgeEmail'}
            if ol_account:
                _res = InternetArchiveAccount.authenticate(
                    email=bridgeEmail, password=bridgePassword, test=test)
                if _res == "ok":
                    ia_account = InternetArchiveAccount.get(
                        email=bridgeEmail, test=test)
                    if OpenLibraryAccount.get_by_link(ia_account.itemname):
                        return {'error': 'account_already_linked'}

                    # avoids Document Update conflict
                    _ol_account = web.ctx.site.store.get(ol_account._key)
                    _ol_account['internetarchive_itemname'] = ia_account.itemname
                    web.ctx.site.store[ol_account._key] = _ol_account

                    audit['link'] = ia_account.itemname
                    audit['has_ia'] = ia_account.itemname
                    return audit
                return {'error': _res}
            elif ia_account:
                _resp = OpenLibraryAccount.authenticate(bridgeEmail, bridgePassword)
                if _resp == "ok":
                    ol_account = OpenLibraryAccount.get(
                        email=bridgeEmail, test=test)
                    if ol_account.itemname:
                        return {'error': 'account_already_linked'}

                    # avoids Document Update conflict
                    _ol_account = web.ctx.site.store.get(ol_account._key)
                    _ol_account['internetarchive_itemname'] = ia_account.itemname
                    web.ctx.site.store[ol_account._key] = _ol_account

                    audit['has_ol'] = ol_account.username
                    return audit
                return {'error': _resp}
        # Create and link new account
        elif email and password and username:
            if ol_account:
                try:
                    ia_account = InternetArchiveAccount.create(
                        username, email, password, test=test)
                    return {'error': 'account_creation_not_implemented'}

                    audit['link'] = ia_account.itemname
                    audit['has_ia'] = ia_account.itemname
                    return audit

                except (ValueError, NotImplementedError) as e:
                    return {'error': str(e)}
            elif ia_account:
                try:
                    ol_account = OpenLibraryAccount.create(
                        username, email, password, test=test, verify=False)

                    # avoics Document Update conflict
                    _ol_account = web.ctx.site.store.get(ol_account._key)
                    _ol_account['internetarchive_itemname'] = ia_account.itemname
                    web.ctx.site.store[ol_account._key] = _ol_account

                    audit['has_ol'] = ol_account.username
                    audit['link'] = ia_account.itemname
                    return audit
                except (ValueError, NotImplementedError) as e:
                    return {'error': str(e)}
            return {'error': 'no_valid_accounts'}
        return {'error': 'missing_fields'}

