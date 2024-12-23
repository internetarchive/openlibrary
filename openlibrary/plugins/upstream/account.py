import json
import logging
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime
from math import ceil
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import urlparse

import requests
import web

import infogami.core.code as core  # noqa: F401 side effects may be needed
from infogami import config
from infogami.infobase.client import ClientException
from infogami.utils import delegate
from infogami.utils.view import (
    add_flash_message,
    render,
    render_template,
    require_login,
)
from openlibrary import accounts
from openlibrary.accounts import (
    InternetArchiveAccount,
    OLAuthenticationError,
    OpenLibraryAccount,
    audit_accounts,
    clear_cookies,
    valid_email,
)
from openlibrary.core import helpers as h
from openlibrary.core import lending, stats
from openlibrary.core.booknotes import Booknotes
from openlibrary.core.bookshelves import Bookshelves
from openlibrary.core.follows import PubSub
from openlibrary.core.lending import (
    get_items_and_add_availability,
    s3_loan_api,
)
from openlibrary.core.observations import Observations
from openlibrary.core.ratings import Ratings
from openlibrary.i18n import gettext as _
from openlibrary.plugins import openlibrary as olib
from openlibrary.plugins.recaptcha import recaptcha
from openlibrary.plugins.upstream import borrow, forms, utils
from openlibrary.plugins.upstream.mybooks import MyBooksTemplate
from openlibrary.utils.dateutil import elapsed_time

if TYPE_CHECKING:
    from openlibrary.plugins.upstream.models import Work

logger = logging.getLogger("openlibrary.account")

CONFIG_IA_DOMAIN: Final = config.get('ia_base_url', 'https://archive.org')
USERNAME_RETRIES = 3
RESULTS_PER_PAGE: Final = 25

# XXX: These need to be cleaned up
send_verification_email = accounts.send_verification_email
create_link_doc = accounts.create_link_doc
sendmail = accounts.sendmail


def get_login_error(error_key):
    """Nesting the LOGIN_ERRORS dictionary inside a function prevents
    an AttributeError with the web.ctx.lang library"""
    LOGIN_ERRORS = {
        "invalid_email": _('The email address you entered is invalid'),
        "account_blocked": _('This account has been blocked'),
        "account_locked": _('This account has been locked'),
        "account_not_found": _(
            'No account was found with this email. Please try again'
        ),
        "account_incorrect_password": _(
            'The password you entered is incorrect. Please try again'
        ),
        "account_bad_password": _('Wrong password. Please try again'),
        "account_not_verified": _(
            'Please verify your Open Library account before logging in'
        ),
        "ia_account_not_verified": _(
            'Please verify your Internet Archive account before logging in'
        ),
        "missing_fields": _('Please fill out all fields and try again'),
        "email_registered": _('This email is already registered'),
        "username_registered": _('This username is already registered'),
        "max_retries_exceeded": _(
            'A problem occurred and we were unable to log you in.'
        ),
        "invalid_s3keys": _(
            'Login attempted with invalid Internet Archive s3 credentials.'
        ),
        "request_timeout": _(
            "Servers are experiencing unusually high traffic, please try again later or email openlibrary@archive.org for help."
        ),
        "undefined_error": _('A problem occurred and we were unable to log you in'),
    }
    return LOGIN_ERRORS[error_key]


class availability(delegate.page):
    path = "/internal/fake/availability"

    def POST(self):
        """Internal private API required for testing on localhost"""
        return delegate.RawText(json.dumps({}), content_type="application/json")


class loans(delegate.page):
    path = "/internal/fake/loans"

    def POST(self):
        """Internal private API required for testing on localhost"""
        return delegate.RawText(json.dumps({}), content_type="application/json")


class xauth(delegate.page):
    path = "/internal/fake/xauth"

    def POST(self):
        """Internal private API required for testing login on localhost
        which normally would have to hit archive.org's xauth
        service. This service is spoofable to return successful and
        unsuccessful login attempts depending on the provided GET parameters
        """
        i = web.input(email='', op=None)
        result = {"error": "incorrect option specified"}
        if i.op == "authenticate":
            result = {
                "success": True,
                "version": 1,
                "values": {
                    "access": 'foo',
                    "secret": 'foo',
                },
            }
        elif i.op == "info":
            result = {
                "success": True,
                "values": {
                    "locked": False,
                    "email": "openlibrary@example.org",
                    "itemname": "@openlibrary",
                    "screenname": "openlibrary",
                    "verified": True,
                },
                "version": 1,
            }
        return delegate.RawText(json.dumps(result), content_type="application/json")


class internal_audit(delegate.page):
    path = "/internal/account/audit"

    def GET(self):
        """Internal API endpoint used for authorized test cases and
        administrators to unlink linked OL and IA accounts.
        """
        i = web.input(
            email='', username='', itemname='', key='', unlink='', new_itemname=''
        )
        if i.key != lending.config_internal_tests_api_key:
            result = {'error': 'Authentication failed for private API'}
        else:
            try:
                result = OpenLibraryAccount.get(
                    email=i.email, link=i.itemname, username=i.username
                )
                if result is None:
                    raise ValueError('Invalid Open Library account email or itemname')
                result.enc_password = 'REDACTED'
                if i.new_itemname:
                    result.link(i.new_itemname)
                if i.unlink:
                    result.unlink()
            except ValueError as e:
                result = {'error': str(e)}

        return delegate.RawText(json.dumps(result), content_type="application/json")


class account_migration(delegate.page):
    path = "/internal/account/migration"

    def GET(self):
        i = web.input(username='', email='', key='')
        if i.key != lending.config_internal_tests_api_key:
            return delegate.RawText(
                json.dumps({'error': 'Authentication failed for private API'}),
                content_type="application/json",
            )
        try:
            if i.username:
                ol_account = OpenLibraryAccount.get(username=i.username)
            elif i.email:
                ol_account = OpenLibraryAccount.get(email=i.email)
        except Exception as e:
            return delegate.RawText(
                json.dumps({'error': 'bad-account'}), content_type="application/json"
            )
        if ol_account:
            ol_account.enc_password = 'REDACTED'
            if ol_account.itemname:
                return delegate.RawText(
                    json.dumps(
                        {
                            'status': 'link-exists',
                            'username': ol_account.username,
                            'itemname': ol_account.itemname,
                            'email': ol_account.email.lower(),
                        }
                    ),
                    content_type="application/json",
                )
            if not ol_account.itemname:
                ia_account = InternetArchiveAccount.get(email=ol_account.email.lower())
                if ia_account:
                    ol_account.link(ia_account.itemname)
                    return delegate.RawText(
                        json.dumps(
                            {
                                'username': ol_account.username,
                                'status': 'link-found',
                                'itemname': ia_account.itemname,
                                'ol-itemname': ol_account.itemname,
                                'email': ol_account.email.lower(),
                                'ia': ia_account,
                            }
                        ),
                        content_type="application/json",
                    )

                password = OpenLibraryAccount.generate_random_password(16)
                ia_account = InternetArchiveAccount.create(
                    ol_account.username or ol_account.displayname,
                    ol_account.email,
                    password,
                    verified=True,
                    retries=USERNAME_RETRIES,
                )
                return delegate.RawText(
                    json.dumps(
                        {
                            'username': ol_account.username,
                            'email': ol_account.email,
                            'itemname': ia_account.itemname,
                            'password': password,
                            'status': 'link-created',
                        }
                    ),
                    content_type="application/json",
                )


class account(delegate.page):
    """Account preferences."""

    @require_login
    def GET(self):
        user = accounts.get_current_user()
        return render.account(user)


class account_create(delegate.page):
    """New account creation.

    Account remains in the pending state until the email is activated.
    """

    path = "/account/create"

    def GET(self):
        f = self.get_form()
        return render['account/create'](f)

    def get_form(self) -> forms.RegisterForm:
        f = forms.Register()
        recap = self.get_recap()
        f.has_recaptcha = recap is not None
        if f.has_recaptcha:
            f.inputs = list(f.inputs) + [recap]
        return f

    def get_recap(self):
        if self.is_plugin_enabled('recaptcha'):
            public_key = config.plugin_invisible_recaptcha.public_key
            private_key = config.plugin_invisible_recaptcha.private_key
            if public_key and private_key:
                return recaptcha.Recaptcha(public_key, private_key)

    def is_plugin_enabled(self, name):
        return (
            name in delegate.get_plugins()
            or "openlibrary.plugins." + name in delegate.get_plugins()
        )

    def POST(self):
        f: forms.RegisterForm = self.get_form()

        if f.validates(web.input()):
            try:
                # Create ia_account: require they activate via IA email
                # and then login to OL. Logging in after activation with
                # IA credentials will auto create and link OL account.

                """NOTE: the values for the notifications must be kept in sync
                with the values in the `MAILING_LIST_KEYS` array in
                https://git.archive.org/ia/petabox/blob/master/www/common/MailSync/Settings.inc
                Currently, per the fundraising/development team, the
                "announcements checkbox" should map to BOTH `ml_best_of` and
                `ml_updates`
                """  # nopep8
                mls = ['ml_best_of', 'ml_updates']
                notifications = mls if f.ia_newsletter.checked else []
                InternetArchiveAccount.create(
                    screenname=f.username.value,
                    email=f.email.value,
                    password=f.password.value,
                    notifications=notifications,
                    verified=False,
                    retries=USERNAME_RETRIES,
                )
                return render['account/verify'](
                    username=f.username.value, email=f.email.value
                )
            except OLAuthenticationError as e:
                f.note = get_login_error(e.__str__())
                from openlibrary.plugins.openlibrary.sentry import sentry

                if sentry.enabled:
                    sentry.capture_exception(e)

        return render['account/create'](f)


del delegate.pages['/account/register']


class account_login_json(delegate.page):
    encoding = "json"
    path = "/account/login"

    def POST(self):
        """Overrides `account_login` and infogami.login to prevent users from
        logging in with Open Library username and password if the
        payload is json. Instead, if login attempted w/ json
        credentials, requires Archive.org s3 keys.
        """
        from openlibrary.plugins.openlibrary.code import (
            BadRequest,  # noqa: F401 side effects may be needed
        )

        d = json.loads(web.data())
        email = d.get('email', "")
        remember = d.get('remember', "")
        access = d.get('access', None)
        secret = d.get('secret', None)
        test = d.get('test', False)

        # Try S3 authentication first, fallback to infogami user, pass
        if access and secret:
            audit = audit_accounts(
                None,
                None,
                require_link=True,
                s3_access_key=access,
                s3_secret_key=secret,
                test=test,
            )
            error = audit.get('error')
            if error:
                resp = {
                    'error': error,
                    'errorDisplayString': get_login_error(error),
                }
                raise olib.code.BadRequest(json.dumps(resp))
            expires = 3600 * 24 * 365 if remember.lower() == 'true' else ""
            web.setcookie(config.login_cookie_name, web.ctx.conn.get_auth_token())
            if audit.get('ia_email'):
                ol_account = OpenLibraryAccount.get(email=audit['ia_email'])
                if ol_account and ol_account.get_user().get_safe_mode() == 'yes':
                    web.setcookie('sfw', 'yes', expires=expires)
                if (
                    ol_account
                    and 'yrg_banner_pref' in ol_account.get_user().preferences()
                ):
                    web.setcookie(
                        ol_account.get_user().preferences()['yrg_banner_pref'],
                        '1',
                        expires=(3600 * 24 * 365),
                    )
        # Fallback to infogami user/pass
        else:
            from infogami.plugins.api.code import login as infogami_login

            infogami_login().POST()


class account_login(delegate.page):
    """Account login.

    Login can fail because of the following reasons:

    * account_not_found: Error message is displayed.
    * account_bad_password: Error message is displayed with a link to reset password.
    * account_not_verified: Error page is displayed with button to "resend verification email".
    """

    path = "/account/login"

    def render_error(self, error_key, i):
        f = forms.Login()
        f.fill(i)
        f.note = get_login_error(error_key)
        return render.login(f)

    def GET(self):
        referer = web.ctx.env.get('HTTP_REFERER', '')
        # Don't set referer if request is from offsite
        parsed_referer = urlparse(referer)
        this_host = web.ctx.host
        if ':' in this_host:
            # Remove port number
            this_host = this_host.split(':', 1)[0]
        if parsed_referer.hostname != this_host:
            referer = None
        i = web.input(redirect=referer)
        f = forms.Login()
        f['redirect'].value = i.redirect
        return render.login(f)

    def POST(self):
        i = web.input(
            username="",
            connect=None,
            password="",
            remember=False,
            redirect='/',
            test=False,
            access=None,
            secret=None,
        )
        email = i.username  # XXX username is now email
        audit = audit_accounts(
            email,
            i.password,
            require_link=True,
            s3_access_key=i.access or web.ctx.env.get('HTTP_X_S3_ACCESS'),
            s3_secret_key=i.secret or web.ctx.env.get('HTTP_X_S3_SECRET'),
            test=i.test,
        )
        if error := audit.get('error'):
            return self.render_error(error, i)

        expires = 3600 * 24 * 365 if i.remember else ""
        web.setcookie('pd', int(audit.get('special_access')) or '', expires=expires)
        web.setcookie(
            config.login_cookie_name, web.ctx.conn.get_auth_token(), expires=expires
        )
        ol_account = OpenLibraryAccount.get(email=email)
        if ol_account and ol_account.get_user().get_safe_mode() == 'yes':
            web.setcookie('sfw', 'yes', expires=expires)
        if ol_account and 'yrg_banner_pref' in ol_account.get_user().preferences():
            web.setcookie(
                ol_account.get_user().preferences()['yrg_banner_pref'],
                '1',
                expires=(3600 * 24 * 365),
            )
        blacklist = [
            "/account/login",
            "/account/create",
        ]
        if i.redirect == "" or any(path in i.redirect for path in blacklist):
            i.redirect = "/account/books"
        stats.increment('ol.account.xauth.login')
        raise web.seeother(i.redirect)

    def POST_resend_verification_email(self, i):
        try:
            ol_login = OpenLibraryAccount.authenticate(i.email, i.password)
        except ClientException as e:
            code = e.get_data().get("code")
            if code != "account_not_verified":
                return self.error("account_incorrect_password", i)

        account = OpenLibraryAccount.get(email=i.email)
        account.send_verification_email()

        title = _("Hi, %(user)s", user=account.displayname)
        message = _(
            "We've sent the verification email to %(email)s. You'll need to read that and click on the verification link to verify your email.",
            email=account.email,
        )
        return render.message(title, message)


class account_logout(delegate.page):
    """Account logout.

    This registers a handler to the /account/logout endpoint in infogami so that additional logic, such as clearing admin cookies,
    can be handled prior to the calling of infogami's standard logout procedure

    """

    path = "/account/logout"

    def POST(self):
        clear_cookies()
        from infogami.core.code import logout as infogami_logout

        return infogami_logout().POST()


class account_verify(delegate.page):
    """Verify user account."""

    path = "/account/verify/([0-9a-f]*)"

    def GET(self, code):
        docs = web.ctx.site.store.values(type="account-link", name="code", value=code)
        if docs:
            doc = docs[0]

            account = accounts.find(username=doc['username'])
            if account and account['status'] != "pending":
                return render['account/verify/activated'](account)
            account.activate()
            user = web.ctx.site.get("/people/" + doc['username'])  # TBD
            return render['account/verify/success'](account)
        else:
            return render['account/verify/failed']()

    def POST(self, code=None):
        """Called to regenerate account verification code."""
        i = web.input(email=None)
        account = accounts.find(email=i.email)
        if not account:
            return render_template("account/verify/failed", email=i.email)
        elif account['status'] != "pending":
            return render['account/verify/activated'](account)
        else:
            account.send_verification_email()
            title = _("Hi, %(user)s", user=account.displayname)
            message = _(
                "We've sent the verification email to %(email)s. You'll need to read that and click on the verification link to verify your email.",
                email=account.email,
            )
            return render.message(title, message)


class account_verify_old(account_verify):
    """Old account verification code.

    This takes username, email and code as url parameters. The new one takes just the code as part of the url.
    """

    path = "/account/verify"

    def GET(self):
        # It is too long since we switched to the new account verification links.
        # All old links must be expired by now.
        # Show failed message without thinking.
        return render['account/verify/failed']()


class account_validation(delegate.page):
    path = '/account/validate'

    @staticmethod
    def ia_username_exists(username):
        url = "https://archive.org/metadata/@%s" % username
        try:
            return bool(requests.get(url).json())
        except (OSError, ValueError):
            return

    @staticmethod
    def validate_username(username):
        ol_account = OpenLibraryAccount.get(username=username)
        if ol_account:
            return _("Username unavailable")

        ia_account = account_validation.ia_username_exists(username)
        if ia_account:
            return _("Username unavailable")

    @staticmethod
    def validate_email(email):
        ol_account = OpenLibraryAccount.get(email=email)
        if ol_account:
            return _('Email already registered')

        ia_account = InternetArchiveAccount.get(email=email)
        if ia_account:
            return _('An Internet Archive account already exists with this email')

    def GET(self):
        i = web.input()
        errors = {'email': None, 'username': None}
        if i.get('email') is not None:
            errors['email'] = self.validate_email(i.email)
        if i.get('username') is not None:
            errors['username'] = self.validate_username(i.username)
        return delegate.RawText(json.dumps(errors), content_type="application/json")


class account_email_verify(delegate.page):
    path = "/account/email/verify/([0-9a-f]*)"

    def GET(self, code):
        if link := accounts.get_link(code):
            username = link['username']
            email = link['email']
            link.delete()
            return self.update_email(username, email)
        else:
            return self.bad_link()

    def update_email(self, username, email):
        if accounts.find(email=email):
            title = _("Email address is already used.")
            message = _(
                "Your email address couldn't be updated. The specified email address is already used."
            )
        else:
            logger.info("updated email of %s to %s", username, email)
            accounts.update_account(username=username, email=email, status="active")
            title = _("Email verification successful.")
            message = _(
                'Your email address has been successfully verified and updated in your account.'
            )
        return render.message(title, message)

    def bad_link(self):
        title = _("Email address couldn't be verified.")
        message = _(
            "Your email address couldn't be verified. The verification link seems invalid."
        )
        return render.message(title, message)


class account_email_verify_old(account_email_verify):
    path = "/account/email/verify"

    def GET(self):
        # It is too long since we switched to the new email verification links.
        # All old links must be expired by now.
        # Show failed message without thinking.
        return self.bad_link()


class account_ia_email_forgot(delegate.page):
    path = "/account/email/forgot-ia"

    def GET(self):
        return render_template('account/email/forgot-ia')

    def POST(self):
        i = web.input(email='', password='')
        err = ""

        if valid_email(i.email):
            act = OpenLibraryAccount.get(email=i.email)
            if act:
                if OpenLibraryAccount.authenticate(i.email, i.password) == "ok":
                    ia_act = act.get_linked_ia_account()
                    if ia_act:
                        return render_template(
                            'account/email/forgot-ia', email=ia_act.email
                        )
                    else:
                        err = "Open Library Account not linked. Login with your Open Library credentials to connect or create an Archive.org account"
                else:
                    err = "Incorrect password"
            else:
                err = "Sorry, this Open Library account does not exist"
        else:
            err = "Please enter a valid Open Library email"
        return render_template('account/email/forgot-ia', err=err)


class account_password_forgot(delegate.page):
    path = "/account/password/forgot"

    def GET(self):
        f = forms.ForgotPassword()
        return render['account/password/forgot'](f)

    def POST(self):
        i = web.input(email='')

        f = forms.ForgotPassword()

        if not f.validates(i):
            return render['account/password/forgot'](f)

        account = accounts.find(email=i.email)

        if account.is_blocked():
            f.note = utils.get_error("account_blocked")
            return render_template('account/password/forgot', f)

        send_forgot_password_email(account.username, i.email)
        return render['account/password/sent'](i.email)


class account_password_reset(delegate.page):
    path = "/account/password/reset/([0-9a-f]*)"

    def GET(self, code):
        docs = web.ctx.site.store.values(type="account-link", name="code", value=code)
        if not docs:
            title = _("Password reset failed.")
            message = "Your password reset link seems invalid or expired."
            return render.message(title, message)

        f = forms.ResetPassword()
        return render['account/password/reset'](f)

    def POST(self, code):
        link = accounts.get_link(code)
        if not link:
            title = _("Password reset failed.")
            message = "The password reset link seems invalid or expired."
            return render.message(title, message)

        username = link['username']
        i = web.input()

        accounts.update_account(username, password=i.password)
        link.delete()
        return render_template("account/password/reset_success", username=username)


class account_audit(delegate.page):
    path = "/account/audit"

    def POST(self):
        """When the user attempts a login, an audit is performed to determine
        whether their account is already linked (in which case we can
        proceed to log the user in), whether there is an error
        authenticating their account, or whether a /account/connect
        must first performed.

        Note: Emails are case sensitive behind the scenes and
        functions which require them as lower will make them so
        """
        i = web.input(email='', password='')
        test = i.get('test', '').lower() == 'true'
        email = i.get('email')
        password = i.get('password')
        result = audit_accounts(email, password, test=test)
        return delegate.RawText(json.dumps(result), content_type="application/json")


class account_privacy(delegate.page):
    path = "/account/privacy"

    @require_login
    def GET(self):
        user = accounts.get_current_user()
        return render['account/privacy'](user.preferences())

    @require_login
    def POST(self):
        i = web.input(public_readlog="", safe_mode="")
        user = accounts.get_current_user()
        if user.get_safe_mode() != 'yes' and i.safe_mode == 'yes':
            stats.increment('ol.account.safe_mode')

        user.save_preferences(i)
        username = user.key.split('/')[-1]
        PubSub.toggle_privacy(username, private=i.public_readlog == 'no')
        web.setcookie(
            'sfw', i.safe_mode, expires="" if i.safe_mode.lower() == 'yes' else -1
        )
        add_flash_message(
            'note', _("Notification preferences have been updated successfully.")
        )
        web.seeother("/account")


class account_notifications(delegate.page):
    path = "/account/notifications"

    @require_login
    def GET(self):
        user = accounts.get_current_user()
        email = user.email
        return render['account/notifications'](user.preferences(), email)

    @require_login
    def POST(self):
        user = accounts.get_current_user()
        user.save_preferences(web.input())
        add_flash_message(
            'note', _("Notification preferences have been updated successfully.")
        )
        web.seeother("/account")


class account_lists(delegate.page):
    path = "/account/lists"

    @require_login
    def GET(self):
        user = accounts.get_current_user()
        raise web.seeother(user.key + '/lists')


class account_my_books_redirect(delegate.page):
    path = "/account/books/(.*)"

    @require_login
    def GET(self, rest='loans'):
        i = web.input(page=1)
        user = accounts.get_current_user()
        username = user.key.split('/')[-1]
        query_params = f'?page={i.page}' if h.safeint(i.page) > 1 else ''
        raise web.seeother(f'/people/{username}/books/{rest}{query_params}')


class account_my_books(delegate.page):
    path = "/account/books"

    @require_login
    def GET(self):
        user = accounts.get_current_user()
        username = user.key.split('/')[-1]
        raise web.seeother(f'/people/{username}/books')


class import_books(delegate.page):
    path = "/account/import"

    @require_login
    def GET(self):
        user = accounts.get_current_user()
        username = user['key'].split('/')[-1]
        template = render['account/import']()
        return MyBooksTemplate(username, 'imports').render(
            header_title=_("Imports and Exports"), template=template
        )


class fetch_goodreads(delegate.page):
    path = "/account/import/goodreads"

    def GET(self):
        raise web.seeother("/account/import")

    @require_login
    def POST(self):
        books, books_wo_isbns = process_goodreads_csv(web.input())
        return render['account/import'](books, books_wo_isbns)


def csv_header_and_format(row: Mapping[str, Any]) -> tuple[str, str]:
    """
    Convert the keys of a dict into csv header and format strings for generating a
    comma separated values string.  This will only be run on the first row of data.
    >>> csv_header_and_format({"item_zero": 0, "one_id_id": 1, "t_w_o": 2, "THREE": 3})
    ('Item Zero,One Id ID,T W O,Three', '{item_zero},{one_id_id},{t_w_o},{THREE}')
    """
    return (  # The .replace("_Id,", "_ID,") converts "Edition Id" --> "Edition ID"
        ",".join(fld.replace("_", " ").title() for fld in row).replace(" Id,", " ID,"),
        ",".join("{%s}" % field for field in row),
    )


@elapsed_time("csv_string")
def csv_string(source: Iterable[Mapping], row_formatter: Callable | None = None) -> str:
    """
    Given a list of dicts, generate comma-separated values where each dict is a row.
    An optional reformatter function can be provided to transform or enrich each dict.
    The order and names of the formatter's output dict keys will determine the order
    and header column titles of the resulting csv string.
    :param source: An iterable of all the rows that should appear in the csv string.
    :param formatter: A Callable that accepts a Mapping and returns a dict.
    >>> csv = csv_string([{"row_id": x, "t w o": 2, "upper": x.upper()} for x in "ab"])
    >>> csv.splitlines()
    ['Row ID,T W O,Upper', 'a,2,A', 'b,2,B']
    """
    if not row_formatter:  # The default formatter reuses the inbound dict unmodified

        def row_formatter(row: Mapping) -> Mapping:
            return row

    def csv_body() -> Iterable[str]:
        """
        On the first row, use csv_header_and_format() to get and yield the csv_header.
        Then use csv_format to yield each row as a string of comma-separated values.
        """
        assert row_formatter, "Placate mypy."
        for i, row in enumerate(source):
            if i == 0:  # Only on first row, make header and format from the dict keys
                csv_header, csv_format = csv_header_and_format(row_formatter(row))
                yield csv_header
            yield csv_format.format(**row_formatter(row))

    return '\n'.join(csv_body())


class export_books(delegate.page):
    path = "/account/export"
    date_format = '%Y-%m-%d %H:%M:%S'

    @require_login
    def GET(self):
        i = web.input(type='')
        filename = ''

        user = accounts.get_current_user()
        username = user.key.split('/')[-1]

        if i.type == 'reading_log':
            data = self.generate_reading_log(username)
            filename = 'OpenLibrary_ReadingLog.csv'
        elif i.type == 'book_notes':
            data = self.generate_book_notes(username)
            filename = 'OpenLibrary_BookNotes.csv'
        elif i.type == 'reviews':
            data = self.generate_reviews(username)
            filename = 'OpenLibrary_Reviews.csv'
        elif i.type == 'lists':
            with elapsed_time("user.get_lists()"):
                lists = user.get_lists(limit=1000)
            with elapsed_time("generate_list_overview()"):
                data = self.generate_list_overview(lists)
            filename = 'Openlibrary_ListOverview.csv'
        elif i.type == 'ratings':
            data = self.generate_star_ratings(username)
            filename = 'OpenLibrary_Ratings.csv'

        web.header('Content-Type', 'text/csv')
        web.header('Content-disposition', f'attachment; filename={filename}')
        return delegate.RawText('' or data, content_type="text/csv")

    def escape_csv_field(self, raw_string: str) -> str:
        """
        Formats given CSV field string such that it conforms to definition outlined
        in RFC #4180.

        Note: We should probably use
        https://docs.python.org/3/library/csv.html
        """
        escaped_string = raw_string.replace('"', '""')
        return f'"{escaped_string}"'

    def get_work_from_id(self, work_id: str) -> "Work":
        """
        Gets work data for a given work ID (OLxxxxxW format), used to access work author, title, etc. for CSV generation.
        """
        work_key = f"/works/{work_id}"
        work: Work = web.ctx.site.get(work_key)
        if not work:
            raise ValueError(f"No Work found for {work_key}.")
        if work.type.key == '/type/redirect':
            # Fetch actual work and resolve redirects before exporting:
            work = web.ctx.site.get(work.location)
            work.resolve_redirect_chain(work_key)
        return work

    def generate_reading_log(self, username: str) -> str:
        bookshelf_map = {1: 'Want to Read', 2: 'Currently Reading', 3: 'Already Read'}

        def get_subjects(work: "Work", subject_type: str) -> str:
            return " | ".join(s.title for s in work.get_subject_links(subject_type))

        def format_reading_log(book: dict) -> dict:
            """
            Adding, deleting, renaming, or reordering the fields of the dict returned
            below will automatically be reflected in the CSV that is generated.
            """
            work_id = f"OL{book['work_id']}W"
            if edition_id := book.get("edition_id") or "":
                edition_id = f"OL{edition_id}M"
            work = self.get_work_from_id(work_id)
            ratings = work.get_rating_stats() or {"average": "", "count": ""}
            ratings_average, ratings_count = ratings.values()
            return {
                "work_id": work_id,
                "title": self.escape_csv_field(work.title),
                "authors": self.escape_csv_field(" | ".join(work.get_author_names())),
                "first_publish_year": work.first_publish_year,
                "edition_id": edition_id,
                "edition_count": work.edition_count,
                "bookshelf": bookshelf_map[work.get_users_read_status(username)],
                "my_ratings": work.get_users_rating(username) or "",
                "ratings_average": ratings_average,
                "ratings_count": ratings_count,
                "has_ebook": work.has_ebook(),
                "subjects": self.escape_csv_field(
                    get_subjects(work=work, subject_type="subject")
                ),
                "subject_people": self.escape_csv_field(
                    get_subjects(work=work, subject_type="person")
                ),
                "subject_places": self.escape_csv_field(
                    get_subjects(work=work, subject_type="place")
                ),
                "subject_times": self.escape_csv_field(
                    get_subjects(work=work, subject_type="time")
                ),
            }

        books = Bookshelves.iterate_users_logged_books(username)
        return csv_string(books, format_reading_log)

    def generate_book_notes(self, username: str) -> str:
        def format_booknote(booknote: Mapping) -> dict:
            escaped_note = booknote['notes'].replace('"', '""')
            return {
                "work_id": f"OL{booknote['work_id']}W",
                "edition_id": f"OL{booknote['edition_id']}M",
                "note": f'"{escaped_note}"',
                "created_on": booknote['created'].strftime(self.date_format),
            }

        return csv_string(Booknotes.select_all_by_username(username), format_booknote)

    def generate_reviews(self, username: str) -> str:
        def format_observation(observation: Mapping) -> dict:
            return {
                "work_id": f"OL{observation['work_id']}W",
                "review_category": f'"{observation["observation_type"]}"',
                "review_value": f'"{observation["observation_value"]}"',
                "created_on": observation['created'].strftime(self.date_format),
            }

        observations = Observations.select_all_by_username(username)
        return csv_string(observations, format_observation)

    def generate_list_overview(self, lists):
        row = {
            "list_id": "",
            "list_name": "",
            "list_description": "",
            "entry": "",
            "created_on": "",
            "last_updated": "",
        }

        def lists_as_csv(lists) -> Iterable[str]:
            for i, list in enumerate(lists):
                if i == 0:  # Only on first row, make header and format from dict keys
                    csv_header, csv_format = csv_header_and_format(row)
                    yield csv_header
                row["list_id"] = list.key.split('/')[-1]
                row["list_name"] = (list.name or '').replace('"', '""')
                row["list_description"] = (list.description or '').replace('"', '""')
                row["created_on"] = list.created.strftime(self.date_format)
                if (last_updated := list.last_modified or "") and isinstance(
                    last_updated, datetime
                ):  # placate mypy
                    last_updated = last_updated.strftime(self.date_format)
                row["last_updated"] = last_updated
                for seed in list.seeds:
                    row["entry"] = seed if isinstance(seed, str) else seed.key
                    yield csv_format.format(**row)

        return "\n".join(lists_as_csv(lists))

    def generate_star_ratings(self, username: str) -> str:

        def format_rating(rating: Mapping) -> dict:
            work_id = f"OL{rating['work_id']}W"
            if edition_id := rating.get("edition_id") or "":
                edition_id = f"OL{edition_id}M"
            work = self.get_work_from_id(work_id)
            return {
                "Work ID": work_id,
                "Edition ID": edition_id,
                "Title": self.escape_csv_field(work.title),
                "Author(s)": self.escape_csv_field(" | ".join(work.get_author_names())),
                "Rating": f"{rating['rating']}",
                "Created On": rating['created'].strftime(self.date_format),
            }

        return csv_string(Ratings.select_all_by_username(username), format_rating)


def _validate_follows_page(page, per_page, hits):
    min_page = 1
    max_page = max(min_page, ceil(hits / per_page))
    if isinstance(page, int):
        return min(max_page, max(min_page, page))
    if isinstance(page, str) and page.isdigit():
        return min(max_page, max(min_page, int(page)))
    return min_page


class my_follows(delegate.page):
    path = r"/people/([^/]+)/(followers|following)"

    def GET(self, username, key=""):
        page_size = 25
        i = web.input(page=1)

        # Validate page ID, force between 1 and max allowed by size and total count
        follow_count = (
            PubSub.count_followers(username)
            if key == 'followers'
            else PubSub.count_following(username)
        )
        page = _validate_follows_page(i.page, page_size, follow_count)

        # Get slice of follows belonging to this page
        offset = max(0, (page - 1) * page_size)
        follows = (
            PubSub.get_followers(username, page_size, offset)
            if key == 'followers'
            else PubSub.get_following(username, page_size, offset)
        )

        mb = MyBooksTemplate(username, 'following')
        manage = key == 'following' and mb.is_my_page
        template = render['account/follows'](
            mb.user, follow_count, page, page_size, follows, manage=manage
        )
        return mb.render(header_title=_(key.capitalize()), template=template)


class account_loans(delegate.page):
    path = "/account/loans"

    @require_login
    def GET(self):
        from openlibrary.core.lending import get_loans_of_user

        user = accounts.get_current_user()
        user.update_loan_status()
        username = user['key'].split('/')[-1]
        mb = MyBooksTemplate(username, 'loans')
        docs = get_loans_of_user(user.key)
        template = render['account/loans'](user, docs)
        return mb.render(header_title=_("Loans"), template=template)


class account_loans_json(delegate.page):
    encoding = "json"
    path = "/account/loans"

    @require_login
    def GET(self):
        user = accounts.get_current_user()
        user.update_loan_status()
        loans = borrow.get_loans(user)
        web.header('Content-Type', 'application/json')
        return delegate.RawText(json.dumps({"loans": loans}))


class account_loan_history(delegate.page):
    path = "/account/loan-history"

    @require_login
    def GET(self):
        i = web.input(page=1)
        page = int(i.page)
        user = accounts.get_current_user()
        username = user['key'].split('/')[-1]
        mb = MyBooksTemplate(username, key='loan_history')
        loan_history_data = get_loan_history_data(page=page, mb=mb)
        template = render['account/loan_history'](
            docs=loan_history_data['docs'],
            current_page=page,
            show_next=loan_history_data['show_next'],
            ia_base_url=CONFIG_IA_DOMAIN,
        )
        return mb.render(header_title=_("Loan History"), template=template)


class account_loan_history_json(delegate.page):
    encoding = "json"
    path = "/account/loan-history"

    @require_login
    def GET(self):
        i = web.input(page=1)
        page = int(i.page)
        user = accounts.get_current_user()
        username = user['key'].split('/')[-1]
        mb = MyBooksTemplate(username, key='loan_history')
        loan_history_data = get_loan_history_data(page=page, mb=mb)
        # Ensure all `docs` are `dicts`, as some are `Edition`s.
        loan_history_data['docs'] = [
            loan.dict() if not isinstance(loan, dict) else loan
            for loan in loan_history_data['docs']
        ]
        web.header('Content-Type', 'application/json')

        return delegate.RawText(json.dumps({"loans_history": loan_history_data}))


class account_waitlist(delegate.page):
    path = "/account/waitlist"

    def GET(self):
        raise web.seeother("/account/loans")


# Disabling because it prevents account_my_books_redirect from working for some reason.
# The purpose of this class is to not show the "Create" link for /account pages since
# that doesn't make any sense.
# class account_others(delegate.page):
#     path = "(/account/.*)"
#
#     def GET(self, path):
#         return render.notfound(path, create=False)


def send_forgot_password_email(username: str, email: str) -> None:
    key = f"account/{username}/password"

    doc = create_link_doc(key, username, email)
    web.ctx.site.store[key] = doc

    link = web.ctx.home + "/account/password/reset/" + doc['code']
    msg = render_template(
        "email/password/reminder", username=username, email=email, link=link
    )
    sendmail(email, msg)


def as_admin(f):
    """Infobase allows some requests only from admin user. This decorator logs in as admin, executes the function and clears the admin credentials."""

    def g(*a, **kw):
        try:
            delegate.admin_login()
            return f(*a, **kw)
        finally:
            web.ctx.headers = []

    return g


def process_goodreads_csv(i):
    import csv

    csv_payload = i.csv if isinstance(i.csv, str) else i.csv.decode()
    csv_file = csv.reader(csv_payload.splitlines(), delimiter=',', quotechar='"')
    header = next(csv_file)
    books = {}
    books_wo_isbns = {}
    for book in list(csv_file):
        _book = dict(zip(header, book))
        isbn = _book['ISBN'] = _book['ISBN'].replace('"', '').replace('=', '')
        isbn_13 = _book['ISBN13'] = _book['ISBN13'].replace('"', '').replace('=', '')
        if isbn != '':
            books[isbn] = _book
        elif isbn_13 != '':
            books[isbn_13] = _book
            books[isbn_13]['ISBN'] = isbn_13
        else:
            books_wo_isbns[_book['Book Id']] = _book
    return books, books_wo_isbns


def get_loan_history_data(page: int, mb: "MyBooksTemplate") -> dict[str, Any]:
    """
    Retrieve IA loan history data for page `page` of the patron's history.

    This will use a patron's S3 keys to query the IA loan history API,
    get the IA IDs, get the OLIDs if available, and and then convert this
    into editions and IA-only items for display in the loan history.

    This returns both editions and IA-only items because the loan history API
    includes items that are not in Open Library, and displaying only IA
    items creates pagination and navigation issues. For further discussion,
    see https://github.com/internetarchive/openlibrary/pull/8375.
    """
    if not (account := OpenLibraryAccount.get(username=mb.username)):
        raise render.notfound(
            "Account for not found for %s" % mb.username, create=False
        )
    s3_keys = web.ctx.site.store.get(account._key).get('s3_keys')
    limit = RESULTS_PER_PAGE
    offset = page * limit - limit
    loan_history = s3_loan_api(
        s3_keys=s3_keys,
        action='user_borrow_history',
        limit=limit + 1,
        offset=offset,
        newest=True,
    ).json()['history']['items']

    # We request limit+1 to see if there is another page of history to display,
    # and then pop the +1 off if it's present.
    show_next = len(loan_history) == limit + 1
    if show_next:
        loan_history.pop()

    ocaids = [loan_record['identifier'] for loan_record in loan_history]
    loan_history_map = {
        loan_record['identifier']: loan_record for loan_record in loan_history
    }

    # Get editions and attach their loan history.
    editions_map = get_items_and_add_availability(ocaids=ocaids)
    for edition in editions_map.values():
        edition_loan_history = loan_history_map.get(edition.get('ocaid'))
        edition['last_loan_date'] = (
            edition_loan_history.get('updatedate') if edition_loan_history else ''
        )

    # Create 'placeholders' dicts for items in the Internet Archive loan history,
    # but absent from Open Library, and then add loan history.
    # ia_only['loan'] isn't set because `LoanStatus.html` reads it as a current
    # loan. No apparenty way to distinguish between current and past loans with
    # this API call.
    ia_only_loans = [{'ocaid': ocaid} for ocaid in ocaids if ocaid not in editions_map]
    for ia_only_loan in ia_only_loans:
        loan_data = loan_history_map[ia_only_loan['ocaid']]
        ia_only_loan['last_loan_date'] = loan_data.get('updatedate', '')
        # Determine the macro to load for loan-history items only.
        ia_only_loan['ia_only'] = True  # type: ignore[typeddict-unknown-key]

    editions_and_ia_loans = list(editions_map.values()) + ia_only_loans
    editions_and_ia_loans.sort(
        key=lambda item: item.get('last_loan_date', ''), reverse=True
    )

    return {
        'docs': editions_and_ia_loans,
        'show_next': show_next,
        'limit': limit,
        'page': page,
    }
