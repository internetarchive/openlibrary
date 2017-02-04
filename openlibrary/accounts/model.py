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


def append_random_suffix(text, limit=9999):
    return '%s_%s' % (text, random.randint(0, limit))

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
    def create(cls, username, email, password, displayname=None,
               verified=False, retries=0, test=False):
        """
        params:
            retries (int) - If the username is unavailable, how many
                            subsequent attempts should be made?
        """
        if cls.get(email=email):
            raise ValueError('email_registered')

        username = username.replace('@', '')
        displayname = displayname or username

        # tests whether a user w/ this username exists
        _user = cls.get(username=username)
        new_username = username
        attempt = 0
        while _user:
            if attempt >= retries:
                ve = ValueError('username_registered')
                ve.value = username
                raise ve
 
            new_username = append_random_suffix(username)
            attempt += 1
            _user = cls.get(username=new_username)
        username = new_username
        if test:
            return cls(**{'itemname': '@' + username,
                          'email': email,
                          'username': username,
                          'displayname': displayname,
                          'test': True
                      })
        try:
            account = web.ctx.site.register(
                username=username,
                email=email,
                password=password,
                displayname=displayname)
        except ClientException as e:
            raise ValueError('something_went_wrong')

        if verified:
            key = "account/%s/verify" % username
            doc = create_link_doc(key, username, email)
            web.ctx.site.store[key] = doc
            web.ctx.site.activate_account(username=username)

        ol_account = cls.get(email=email)
        return ol_account

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
        match = web.ctx.site.store.values(
            type="account", name="username", value=username, limit=1)

        if len(match):
            return cls(match[0])

        lower_match = web.ctx.site.store.values(
            type="account", name="lusername", value=username, limit=1)

        if len(lower_match):
            return cls(lower_match[0])

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
        """Careful, this will save any other changes to the ol user object as
        well
        """
        _ol_account = web.ctx.site.store.get(self._key)
        _ol_account['internetarchive_itemname'] = None
        web.ctx.site.store[self._key] = _ol_account
        self.internetarchive_itemname = None

    def link(self, itemname):
        """Careful, this will save any other changes to the ol user object as
        well
        """
        _ol_account = web.ctx.site.store.get(self._key)
        _ol_account['internetarchive_itemname'] = itemname
        web.ctx.site.store[self._key] = _ol_account
        self.internetarchive_itemname = itemname

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
    def create(cls, screenname, email, password, retries=0,
               verified=False, test=None):
        screenname = screenname.replace('@', '')  # remove IA @
        if cls.get(email=email):
            raise ValueError('email_registered')

        _screenname = screenname
        attempt = 0
        while True:
            response = cls.xauth(
                'create', test=test, email=email, password=password,
                screenname=_screenname, verified=verified)

            if response.get('success'):
                ia_account = cls.get(email=email)
                if test:
                    ia_account.test = True
                return ia_account

            elif 'screenname' not in response.get('values', {}):
                errors = '_'.join(response.get('values', {}))
                raise ValueError(errors)

            elif attempt >= retries:
                ve = ValueError('username_registered')
                ve.value = _screenname
                raise ve

            _screenname = append_random_suffix(screenname)
            attempt += 1            

    @classmethod
    def xauth(cls, service, test=None, **data):
        url = "%s?op=%s" % (lending.IA_XAUTH_API_URL, service)
        data.update({
            'client_access': lending.config_ia_ol_xauth_s3.get('s3_key'),
            'client_secret': lending.config_ia_ol_xauth_s3.get('s3_secret')
        })
        payload = simplejson.dumps(data)
        if test:
            url += "&developer=%s" % test
        try:
            req = urllib2.Request(url, payload, {
                'Content-Type': 'application/json'})
            f = urllib2.urlopen(req)
            response = f.read()
            f.close()
        except urllib2.HTTPError as e:
            try:
                response = e.read()
            except simplejson.decoder.JSONDecodeError:
                return {'error': e.read(), 'code': e.code}
        return simplejson.loads(response)

    @classmethod
    def get(cls, email, test=False, _json=False):
        response = cls.xauth(email=email, test=test, service="info")
        if 'success' in response:
            values = response.get('values', {})
            return values if _json else cls(**values)

    @classmethod
    def authenticate(cls, email, password, test=False):
        response = cls.xauth('authenticate', test=test, **{
            "email": email,
            "password": password
        })
        return ("ok" if response.get('success') is True else
                response.get('values', {}).get('reason'))


def audit_accounts(email, password, test=False):
    if not valid_email(email):
        return {'error': 'invalid_email'}

    audit = {
        'authenticated': False,
        'has_ia': False,
        'has_ol': False,
        'link': False
    }

    ol_login = OpenLibraryAccount.authenticate(email, password)
    ia_login = InternetArchiveAccount.authenticate(email, password)

    if any([err in (ol_login, ia_login) for err
            in ['account_blocked', 'account_locked']]):
        return {'error': 'account_blocked'}

    # One of the accounts must authenticate w/o error
    if "ok" not in (ol_login, ia_login):
        for resp in (ol_login, ia_login):
            if resp != "account_not_found":
                return {'error': resp}
        return {'error': 'account_not_found'}

    elif ia_login == "ok":
        ia_account = InternetArchiveAccount.get(email=email, test=test)

        audit['authenticated'] = 'ia'
        audit['has_ia'] = email

        # Get the OL account which links to this IA account, if
        # one exists (i.e. this IA account could be linked to an
        # OL account with a different email)
        ol_account = OpenLibraryAccount.get(link=ia_account.itemname, test=test)
        link = ol_account.itemname if ol_account else None

        # If no linked account was found but there's an ol_account
        # having the same email as this IA account, mark them to
        # be linked
        if not link:
            ol_account = OpenLibraryAccount.get(email=email, test=test)
            link = ia_account.itemname if ol_account else None

        # So long as there's either a linked OL account, or an OL
        # account with the same email, set them as linked (and let the
        # finalize logic link them, if necessary)
        if ol_account:
            if not ol_account.verified:
                return {'error': 'account_not_verified'}
            if ol_account.blocked:
                return {'error': 'account_blocked'}
            audit['link'] = link
            audit['has_ol'] = ol_account.email

            # Kludge so if a user logs in with IA credentials, we
            # can fetch the linked OL account and set an
            # auth_token even when we don't have the OL user's
            # password in order to perform web.ctx.site.login.
            # Their auth checks out via IA, set their auth_token for OL
            web.ctx.conn.set_auth_token(ol_account.generate_login_code())

    elif ol_login == "ok":
        ol_account = OpenLibraryAccount.get(email=email, test=test)
        audit['authenticated'] = 'ol'
        audit['has_ol'] = email

        ia_account = InternetArchiveAccount.get(email=email, test=test)

        # Should get the IA account linked to this OL account, if one
        # exists. However, xauthn API doesn't yet support `info` by
        # itemname. Fortunately, we have all the info we need at this
        # stage for the client to be satisfied.
        if ol_account.itemname:
            audit['has_ia'] = ol_account.itemname  # XXX should be email
            audit['link'] = ol_account.itemname
            return audit  # special case; unable to get ia acc

        # If the OL account is not linked but there exists an IA
        # account having the same email,
        elif ia_account:
            if not ia_account.verified:
                return {'error': 'account_not_verified'}
            if ia_account.locked:
                return {'error': 'account_blocked'}
            audit['has_ia'] = ia_account.itemname
            audit['link'] = ia_account.itemname

    # Links the accounts if they can be and are not already:
    if (audit['has_ia'] and audit['has_ol'] and audit['authenticated']):
        ol_account = OpenLibraryAccount.get(email=audit['has_ol'], test=test)
        if not ol_account.itemname:
            ol_account.link(audit['link'])

    return audit

def create_accounts(email, password, bridgeEmail="", bridgePassword="",
                    username="", test=False):

    retries = 0 if test else 10
    audit = audit_accounts(email, password)

    if 'error' in audit or (audit['link'] and audit['authenticated']):
        return audit

    ia_account = (InternetArchiveAccount.get(email=audit['has_ia'])
                  if audit.get('has_ia', False) else None)
    ol_account = (OpenLibraryAccount.get(email=audit['has_ol'])
                  if audit.get('has_ol', False) else None)

    # Make sure at least one account exists
    if ia_account and ol_account:
        if not audit['link']:
            if ia_account.locked or ol_account.blocked():
                return {'error': 'account_blocked'}
            audit['link'] = ia_account.itemname
            ol_account.link(ia_account.itemname)
        return audit
    elif not (ia_account or ol_account):
        return {'error': 'account_not_found'}

    # Create and link new account
    if email and password:
        if ol_account:
            try:
                ol_account_username = (
                    username or ol_account.displayname
                    or ol_account.username)
                
                ia_account = InternetArchiveAccount.create(
                    ol_account_username, email, password,
                    retries=retries, verified=True, test=test)

                audit['link'] = ia_account.itemname
                audit['has_ia'] = ia_account.email
                audit['has_ol'] = ol_account.email
                if not test:
                    ol_account.link(ia_account.itemname)
                return audit
            except ValueError as e:
                return {'error': 'max_retries_exceeded', 'msg': str(e)}
        elif ia_account:
            try:
                # always take screen name 
                ia_account_screenname = ia_account.screenname
                ia_account_itemname = ia_account.itemname
                ol_account = OpenLibraryAccount.create(
                    ia_account_itemname, email, password,
                    displayname=ia_account_itemname,
                    retries=retries, verified=True, test=test)
                audit['has_ol'] = ol_account.email
                audit['has_ia'] = ia_account.email
                audit['link'] = ia_account.itemname
                if not test:
                    ol_account.link(ia_account.itemname)
                return audit
            except ValueError as e:
                return {'error': 'max_retries_exceeded', 'msg': str(e)}
        return {'error': 'account_not_found'}
    return {'error': 'missing_fields'}


def link_accounts(email, password, bridgeEmail="", bridgePassword="",
                  username="", test=False):

    audit = audit_accounts(email, password)

    if 'error' in audit or (audit['link'] and audit['authenticated']):
        return audit

    ia_account = (InternetArchiveAccount.get(email=audit['has_ia'])
                  if audit.get('has_ia', False) else None)
    ol_account = (OpenLibraryAccount.get(email=audit['has_ol'])
                  if audit.get('has_ol', False) else None)

    # Make sure at least one account exists
    if ia_account and ol_account:
        if not audit['link']:
            if ia_account.locked or ol_account.blocked():
                return {'error': 'account_blocked'}
            audit['link'] = ia_account.itemname
            ol_account.link(ia_account.itemname)
        return audit
    elif not (ia_account or ol_account):
        return {'error': 'account_not_found'}

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

                ol_account.link(ia_account.itemname)
                audit['link'] = ia_account.itemname
                audit['has_ia'] = ia_account.email
                audit['has_ol'] = ol_account.email
                return audit
            return {'error': _res}
        elif ia_account:
            _resp = OpenLibraryAccount.authenticate(
                bridgeEmail, bridgePassword)
            if _resp == "ok":
                ol_account = OpenLibraryAccount.get(
                    email=bridgeEmail, test=test)
                if ol_account.itemname:
                    return {'error': 'account_already_linked'}

                audit['has_ia'] = ia_account.email
                audit['has_ol'] = ol_account.email
                audit['link'] = ia_account.itemname
                ol_account.link(ia_account.itemname)
                return audit
            return {'error': _resp}
        return {'error': 'account_not_found'}
    return {'error': 'missing_fields'}
