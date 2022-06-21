"""

"""
import time
import datetime
import hashlib
import hmac
import random
import string
import uuid
import logging
import requests

from validate_email import validate_email
import web

from infogami import config
from infogami.utils.view import render_template, public
from infogami.infobase.client import ClientException

from openlibrary.core import stats, helpers
from openlibrary.core.booknotes import Booknotes
from openlibrary.core.bookshelves import Bookshelves
from openlibrary.core.observations import Observations
from openlibrary.core.ratings import Ratings

try:
    from simplejson.errors import JSONDecodeError
except ImportError:
    from json.decoder import JSONDecodeError  # type: ignore[misc]

logger = logging.getLogger("openlibrary.account.model")


def append_random_suffix(text, limit=9999):
    return f'{text}{random.randint(0, limit)}'


def valid_email(email):
    return validate_email(email)


def sendmail(to, msg, cc=None):
    cc = cc or []
    if config.get('dummy_sendmail'):
        message = (
            ''
            + 'To: '
            + to
            + '\n'
            + 'From:'
            + config.from_address
            + '\n'
            + 'Subject:'
            + msg.subject
            + '\n'
            + '\n'
            + web.safestr(msg)
        )

        print("sending email", message, file=web.debug)
    else:
        web.sendmail(
            config.from_address,
            to,
            subject=msg.subject.strip(),
            message=web.safestr(msg),
            cc=cc,
        )


def verify_hash(secret_key, text, hash):
    """Verifies if the hash is generated"""
    salt = hash.split('$', 1)[0]
    return generate_hash(secret_key, text, salt) == hash


def generate_hash(secret_key, text, salt=None):
    if not isinstance(secret_key, bytes):
        secret_key = secret_key.encode('utf-8')
    salt = (
        salt
        or hmac.HMAC(
            secret_key, str(random.random()).encode('utf-8'), hashlib.md5
        ).hexdigest()[:5]
    )
    hash = hmac.HMAC(
        secret_key, (salt + web.safestr(text)).encode('utf-8'), hashlib.md5
    ).hexdigest()
    return f'{salt}${hash}'


def get_secret_key():
    return config.infobase['secret_key']


def generate_uuid():
    return str(uuid.uuid4()).replace("-", "")


def send_verification_email(username, email):
    """Sends account verification email."""
    key = "account/%s/verify" % username

    doc = create_link_doc(key, username, email)
    web.ctx.site.store[key] = doc

    link = web.ctx.home + "/account/verify/" + doc['code']
    msg = render_template(
        "email/account/verify", username=username, email=email, password=None, link=link
    )
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
        "expires_on": expires.isoformat(),
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
        return t and helpers.parse_datetime(t)

    @property
    def activated_on(self):
        user = self.get_user()
        return user and user.created

    @property
    def displayname(self):
        doc = self.get_user()
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
        except ClientException as e:
            code = e.get_data().get("code")
            return code
        else:
            self['last_login'] = datetime.datetime.utcnow().isoformat()
            self._save()
            return "ok"

    @classmethod
    def generate_random_password(cls, n=12):
        return ''.join(
            random.SystemRandom().choice(string.ascii_uppercase + string.digits)
            for _ in range(n)
        )

    def generate_login_code(self):
        """Returns a string that can be set as login cookie to log in as this user."""
        user_key = "/people/" + self.username
        t = datetime.datetime(*time.gmtime()[:6]).isoformat()
        text = f"{user_key},{t}"
        return text + "," + generate_hash(get_secret_key(), text)

    def _save(self):
        """Saves this account in store."""
        web.ctx.site.store[self._key] = self

    @property
    def last_login(self):
        """Returns the last_login time of the user, if available.

        The `last_login` will not be available for accounts, who haven't
        been logged in after this feature is added.
        """
        t = self.get("last_login")
        return t and helpers.parse_datetime(t)

    def get_user(self):
        """A user is where preferences are attached to an account. An
        "Account" is outside of infogami in a separate table and is
        used to store private user information.

        :rtype: User
        :returns: Not an Account obj, but a /people/xxx User
        """
        key = "/people/" + self.username
        return web.ctx.site.get(key)

    def get_creation_info(self):
        key = "/people/" + self.username
        doc = web.ctx.site.get(key)
        return doc.get_creation_info()

    def get_activation_link(self):
        key = "account/%s/verify" % self.username
        doc = web.ctx.site.store.get(key)
        if doc:
            return Link(doc)
        else:
            return False

    def get_password_reset_link(self):
        key = "account/%s/password" % self.username
        doc = web.ctx.site.store.get(key)
        if doc:
            return Link(doc)
        else:
            return False

    def get_links(self):
        """Returns all the verification links present in the database."""
        return web.ctx.site.store.values(
            type="account-link", name="username", value=self.username
        )

    def get_tags(self):
        """Returns list of tags that this user has."""
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
        """Enables/disables the bot flag."""
        self.bot = flag
        self._save()

    def anonymize(self, test=False):
        # Generate new unique username for patron:
        # Note: Cannot test get_activation_link() locally
        uuid = self.get_activation_link()['code'] if self.get_activation_link() else generate_uuid()
        new_username = f'anonymous-{uuid}'
        results = {'new_username': new_username}

        # Delete all of the patron's book notes:
        results['booknotes_count'] = Booknotes.delete_all_by_username(self.username, _test=test)

        # Anonymize patron's username in OL DB tables:
        results['ratings_count'] = Ratings.update_username(self.username, new_username, _test=test)
        results['observations_count'] = Observations.update_username(self.username, new_username, _test=test)
        results['bookshelves_count'] = Bookshelves.update_username(self.username, new_username, _test=test)

        if not test:
            patron = self.get_user()
            email = self.email
            username = self.username

            # Remove patron from all usergroups:
            for grp in patron.usergroups:
                grp.remove_user(patron.key)

            # Set preferences to default:
            patron.save_preferences({
                'updates': 'no',
                'public_readlog': 'no'
            })

            # Clear patron's profile page:
            data = {'key': patron.key, 'type': '/type/delete'}
            patron.set_data(data)

            # Remove account information from store:
            del web.ctx.site.store[f'account/{username}']
            del web.ctx.site.store[f'account/{username}/verify']
            del web.ctx.site.store[f'account/{username}/password']
            del web.ctx.site.store[f'account-email/{email}']

        return results

    @property
    def itemname(self):
        """Retrieves the Archive.org itemname which links Open Library and
        Internet Archive accounts
        """
        return getattr(self, 'internetarchive_itemname', None)

    def get_linked_ia_account(self):
        if self.itemname:
            act = InternetArchiveAccount.xauth('info', itemname=self.itemname)
            if 'values' in act and 'email' in act['values']:
                return InternetArchiveAccount.get(email=act['values']['email'])

    def render_link(self):
        return f'<a href="/people/{self.username}">{web.net.htmlquote(self.displayname)}</a>'


class OpenLibraryAccount(Account):
    @classmethod
    def create(
        cls,
        username,
        email,
        password,
        displayname=None,
        verified=False,
        retries=0,
        test=False,
    ):
        """
        Args:
            username (unicode) - the username (slug) of the account.
                                 Usernames must be unique
            email (unicode) - the login and email of the account
            password (unicode)
            displayname (unicode) - human readable, changeable screenname
            retries (int) - If the username is unavailable, how many
                            subsequent attempts should be made to find
                            an available username.
        """
        if cls.get(email=email):
            raise ValueError('email_registered')

        username = username[1:] if username[0] == '@' else username
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
            return cls(
                **{
                    'itemname': '@' + username,
                    'email': email,
                    'username': username,
                    'displayname': displayname,
                    'test': True,
                }
            )
        try:
            account = web.ctx.site.register(
                username=username,
                email=email,
                password=password,
                displayname=displayname,
            )
        except ClientException as e:
            raise ValueError('something_went_wrong')

        if verified:
            key = "account/%s/verify" % username
            doc = create_link_doc(key, username, email)
            web.ctx.site.store[key] = doc
            web.ctx.site.activate_account(username=username)

        ol_account = cls.get(email=email)

        # Update user preferences; reading log public by default
        from openlibrary.accounts import RunAs

        with RunAs(username):
            ol_account.get_user().save_preferences({'public_readlog': 'yes'})

        return ol_account

    @classmethod
    def get(cls, link=None, email=None, username=None, key=None, test=False):
        """Utility method retrieve an openlibrary account by its email,
        username or archive.org itemname (i.e. link)
        """
        if link:
            return cls.get_by_link(link, test=test)
        elif email:
            return cls.get_by_email(email, test=test)
        elif username:
            return cls.get_by_username(username, test=test)
        elif key:
            return cls.get_by_key(key, test=test)
        raise ValueError("Open Library email or Archive.org itemname required.")

    @classmethod
    def get_by_key(cls, key, test=False):
        username = key.split('/')[-1]
        return cls.get_by_username(username)

    @classmethod
    def get_by_username(cls, username, test=False):
        """Retrieves and OpenLibraryAccount by username if it exists or"""
        match = web.ctx.site.store.values(
            type="account", name="username", value=username, limit=1
        )

        if len(match):
            return cls(match[0])

        lower_match = web.ctx.site.store.values(
            type="account", name="lusername", value=username, limit=1
        )

        if len(lower_match):
            return cls(lower_match[0])

        return None

    @classmethod
    def get_by_link(cls, link, test=False):
        """
        :rtype: OpenLibraryAccount or None
        """
        ol_accounts = web.ctx.site.store.values(
            type="account", name="internetarchive_itemname", value=link
        )
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
        email = email.strip()
        email_doc = web.ctx.site.store.get(
            "account-email/" + email
        ) or web.ctx.site.store.get("account-email/" + email.lower())
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
        stats.increment('ol.account.xauth.unlinked')

    def link(self, itemname):
        """Careful, this will save any other changes to the ol user object as
        well
        """
        itemname = itemname if itemname.startswith('@') else '@%s' % itemname

        _ol_account = web.ctx.site.store.get(self._key)
        _ol_account['internetarchive_itemname'] = itemname
        web.ctx.site.store[self._key] = _ol_account
        self.internetarchive_itemname = itemname
        stats.increment('ol.account.xauth.linked')

    def save_s3_keys(self, s3_keys):
        _ol_account = web.ctx.site.store.get(self._key)
        _ol_account['s3_keys'] = s3_keys
        web.ctx.site.store[self._key] = _ol_account
        self.s3_keys = s3_keys

    @classmethod
    def authenticate(cls, email, password, test=False):
        ol_account = cls.get(email=email, test=test)
        if not ol_account:
            return "account_not_found"
        if ol_account.is_blocked():
            return "account_blocked"
        try:
            web.ctx.site.login(ol_account.username, password)
        except ClientException as e:
            code = e.get_data().get("code")
            return code
        else:
            return "ok"


class InternetArchiveAccount(web.storage):
    def __init__(self, **kwargs):
        for k in kwargs:
            setattr(self, k, kwargs[k])

    @classmethod
    def create(
        cls,
        screenname,
        email,
        password,
        notifications=None,
        retries=0,
        verified=False,
        test=None,
    ):
        """
        :param unicode screenname: changeable human readable archive.org username.
            The slug / itemname is generated automatically from this value.
        :param unicode email:
        :param unicode password:
        :param List[Union[
                Literal['ml_best_of'], Literal['ml_donors'],
                Literal['ml_events'], Literal['ml_updates']
            ]] notifications:
            newsletters to subscribe user to (NOTE: these must be kept in sync
            with the values in the `MAILING_LIST_KEYS` array in
            https://git.archive.org/ia/petabox/blob/master/www/common/MailSync/Settings.inc)
        :param int retries: If the username is unavailable, how many
            subsequent attempts should be made to find an available
            username.
        """
        email = email.strip().lower()
        screenname = screenname[1:] if screenname[0] == '@' else screenname
        notifications = notifications or []

        if cls.get(email=email):
            raise ValueError('email_registered')

        if not screenname:
            raise ValueError('screenname required')

        _screenname = screenname
        attempt = 0
        while True:
            response = cls.xauth(
                'create',
                email=email,
                password=password,
                screenname=_screenname,
                notifications=notifications,
                test=test,
                verified=verified,
                service='openlibrary',
            )

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
    def xauth(cls, op, test=None, s3_key=None, s3_secret=None, xauth_url=None, **data):
        """
        See https://git.archive.org/ia/petabox/tree/master/www/sf/services/xauthn
        """
        from openlibrary.core import lending

        url = xauth_url or lending.config_ia_xauth_api_url
        params = {'op': op}
        data.update(
            {
                'access': s3_key or lending.config_ia_ol_xauth_s3.get('s3_key'),
                'secret': s3_secret or lending.config_ia_ol_xauth_s3.get('s3_secret'),
            }
        )

        # Currently, optional parameters, like `service` are passed as
        # **kwargs (i.e. **data). The xauthn service uses the named
        # parameter `activation-type` which contains a dash and thus
        # is unsuitable as a kwarg name. Therefore, if we're
        # performing an account `create` xauthn operation and the
        # `service` parameter is present, we need to rename `service`
        # as `activation-type` so it is forwarded correctly to xauth:
        if op == 'create' and 'service' in data:
            data['activation-type'] = data.pop('service')

        if test:
            params['developer'] = test

        response = requests.post(url, params=params, json=data)
        try:
            # This API should always return json, even on error (Unless
            # the server is down or something :P)
            return response.json()
        except ValueError:
            return {'error': response.text, 'code': response.status_code}

    @classmethod
    def s3auth(cls, access_key, secret_key):
        """Authenticates an Archive.org user based on s3 keys"""
        from openlibrary.core import lending

        url = lending.config_ia_s3_auth_url
        try:
            response = requests.get(
                url,
                headers={
                    'Content-Type': 'application/json',
                    'authorization': f'LOW {access_key}:{secret_key}',
                },
            )
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as e:
            return {'error': e.response.text, 'code': e.response.status_code}
        except JSONDecodeError as e:
            return {'error': e.message, 'code': response.status_code}

    @classmethod
    def get(
        cls, email, test=False, _json=False, s3_key=None, s3_secret=None, xauth_url=None
    ):
        email = email.strip().lower()
        response = cls.xauth(
            email=email,
            test=test,
            op="info",
            s3_key=s3_key,
            s3_secret=s3_secret,
            xauth_url=xauth_url,
        )
        if 'success' in response:
            values = response.get('values', {})
            return values if _json else cls(**values)

    @classmethod
    def authenticate(cls, email, password, test=False):
        email = email.strip().lower()
        response = cls.xauth(
            'authenticate', test=test, **{"email": email, "password": password}
        )
        if not response.get('success'):
            reason = response['values'].get('reason')
            if reason and reason == 'account_not_verified':
                response['values']['reason'] = 'ia_account_not_verified'
        return response


def audit_accounts(
    email,
    password,
    require_link=False,
    s3_access_key=None,
    s3_secret_key=None,
    test=False,
):
    """Performs an audit of the IA or OL account having this email.

    The audit:
    - verifies the password is correct for this account
    - aborts if any sort of error (e.g. account blocked, unverified)
    - reports whether the account is linked (to a secondary account)
    - if unlinked, reports whether a secondary account exists w/
      matching email

    Args:
        email (unicode)
        password (unicode)
        require_link (bool) - if True, returns `accounts_not_connected`
                              if accounts are not linked
        test (bool) - not currently used; is there to allow testing in
                      the absence of archive.org dependency
    """

    if s3_access_key and s3_secret_key:
        r = InternetArchiveAccount.s3auth(s3_access_key, s3_secret_key)
        if not r.get('authorized', False):
            return {'error': 'invalid_s3keys'}
        ia_login = {'success': True}
        email = r['username']
    else:
        if not valid_email(email):
            return {'error': 'invalid_email'}
        ia_login = InternetArchiveAccount.authenticate(email, password)

    if 'values' in ia_login and any(
        ia_login['values'].get('reason') == err
        for err in ['account_blocked', 'account_locked']
    ):
        return {'error': 'account_locked'}

    if not ia_login.get('success'):
        # Prioritize returning other errors over `account_not_found`
        if ia_login['values'].get('reason') != "account_not_found":
            return {'error': ia_login['values'].get('reason')}
        return {'error': 'account_not_found'}

    else:
        ia_account = InternetArchiveAccount.get(email=email, test=test)

        # Get the OL account which links to this IA account
        ol_account = OpenLibraryAccount.get(link=ia_account.itemname, test=test)
        link = ol_account.itemname if ol_account else None

        # The fact that there is no link implies no Open Library
        # account exists containing a link to this Internet Archive
        # account...
        if not link:
            # then check if there's an Open Library account which shares
            # the same email as this IA account.
            ol_account = OpenLibraryAccount.get(email=email, test=test)

            # If an Open Library account with a matching email account exist...
            if ol_account:
                # Check whether it is linked already, i.e. has an itemname
                # set. We already determined that no OL account is
                # linked to our IA account. Therefore this Open
                # Library account having the same email as our IA
                # account must have been linked to a different
                # Internet Archive account.
                if ol_account.itemname:
                    return {'error': 'wrong_ia_account'}

        # At this point, it must either be the case that (a)
        # `ol_account` already links to our IA account (in which case
        # `link` has a correct value), (b) that an unlinked
        # `ol_account` shares the same email as our IA account and
        # thus can and should be safely linked to our IA account, or
        # (c) no `ol_account` which is linked or can be linked has
        # been found and therefore, assuming
        # lending.config_ia_auth_only is enabled, we need to create
        # and link it.
        if not ol_account:
            if not password:
                raise {'error': 'link_attempt_requires_password'}
            try:
                ol_account = OpenLibraryAccount.create(
                    ia_account.itemname,
                    email,
                    password,
                    displayname=ia_account.screenname,
                    verified=True,
                    retries=5,
                    test=test,
                )
            except ValueError as e:
                return {'error': 'max_retries_exceeded'}

            ol_account.link(ia_account.itemname)
            stats.increment('ol.account.xauth.ia-auto-created-ol')

        # So long as there's either a linked OL account, or an unlinked OL
        # account with the same email, set them as linked (and let the
        # finalize logic link them, if needed)
        else:
            if not ol_account.itemname:
                ol_account.link(ia_account.itemname)
                stats.increment('ol.account.xauth.auto-linked')
            if not ol_account.verified:
                # The IA account is activated (verifying the
                # integrity of their email), so we make a judgement
                # call to safely activate them.
                ol_account.activate()
            if ol_account.blocked:
                return {'error': 'account_blocked'}

    if require_link:
        ol_account = OpenLibraryAccount.get(link=ia_account.itemname, test=test)
        if ol_account and not ol_account.itemname:
            return {'error': 'accounts_not_connected'}

    if 'values' in ia_login:
        s3_keys = {
            'access': ia_login['values'].pop('access'),
            'secret': ia_login['values'].pop('secret'),
        }
        ol_account.save_s3_keys(s3_keys)

    # When a user logs in with OL credentials, the
    # web.ctx.site.login() is called with their OL user
    # credentials, which internally sets an auth_token
    # enabling the user's session.  The web.ctx.site.login
    # method requires OL credentials which are not present in
    # the case where a user logs in with their IA
    # credentials. As a result, when users login with their
    # valid IA credentials, the following kludge allows us to
    # fetch the OL account linked to their IA account, bypass
    # this web.ctx.site.login method (which requires OL
    # credentials), and directly set an auth_token to
    # enable the user's session.
    web.ctx.conn.set_auth_token(ol_account.generate_login_code())
    return {
        'authenticated': True,
        'special_access': getattr(ia_account, 'has_disability_access', False),
        'ia_email': ia_account.email,
        'ol_email': ol_account.email,
        'ia_username': ia_account.screenname,
        'ol_username': ol_account.username,
        'link': ol_account.itemname,
    }


@public
def get_internet_archive_id(key):
    username = key.split('/')[-1]
    return OpenLibraryAccount.get(username=username).itemname
