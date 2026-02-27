import csv
import io
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from math import ceil
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import urlparse

import requests
import web

import infogami.core.code as core  # noqa: F401 side effects may be needed
from infogami import config
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
    RunAs,
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
from openlibrary.core.models import SubjectType
from openlibrary.core.observations import Observations
from openlibrary.core.ratings import Ratings
from openlibrary.i18n import gettext as _
from openlibrary.plugins import openlibrary as olib
from openlibrary.plugins.openlibrary.pd import get_pd_options, get_pd_org
from openlibrary.plugins.recaptcha import recaptcha
from openlibrary.plugins.upstream import borrow, forms
from openlibrary.plugins.upstream.mybooks import MyBooksTemplate
from openlibrary.utils.dateutil import elapsed_time

if TYPE_CHECKING:
    from openlibrary.plugins.upstream.models import User, Work

logger = logging.getLogger("openlibrary.account")

CONFIG_IA_DOMAIN: Final = config.get('ia_base_url', 'https://archive.org')
USERNAME_RETRIES = 3
RESULTS_PER_PAGE: Final = 25

# XXX: These need to be cleaned up
create_link_doc = accounts.create_link_doc


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
        "bad_email": _("Email provider not recognized."),
        "bad_password": _("Password requirements not met."),
        "undefined_error": _('A problem occurred and we were unable to log you in'),
        "security_error": _(
            "Login or registration attempt hit an unexpected error, please try again or contact info@archive.org"
        ),
    }
    return (
        LOGIN_ERRORS[error_key]
        if error_key in LOGIN_ERRORS
        else _("Request failed with error code: %(error_code)s", error_code=error_key)
    )


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
                result = None
                if i.itemname:
                    result = OpenLibraryAccount.get_by_link(i.itemname)
                elif i.email:
                    result = OpenLibraryAccount.get_by_email(i.email)
                elif i.username:
                    result = OpenLibraryAccount.get_by_username(i.username)
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
                ol_account = OpenLibraryAccount.get_by_username(i.username)
            elif i.email:
                ol_account = OpenLibraryAccount.get_by_email(i.email)
        except Exception:
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
        return render['account/create'](f, pd_options=get_pd_options())

    def get_form(self) -> forms.RegisterForm:
        f = forms.Register()
        recap = self.get_recap()
        f.has_recaptcha = recap is not None
        if f.has_recaptcha:
            f.inputs = list(f.inputs) + [recap]
        return f

    def get_recap(self):
        public_key = config.plugin_invisible_recaptcha.public_key
        private_key = config.plugin_invisible_recaptcha.private_key
        if public_key and private_key:
            return recaptcha.Recaptcha(public_key, private_key)

    def POST(self):
        f: forms.RegisterForm = self.get_form()

        if f.validates(web.input(email="")):
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
                notifications = mls if "ia_newsletter" in web.input() else []
                InternetArchiveAccount.create(
                    screenname=f.username.value,
                    email=f.email.value,
                    password=f.password.value,
                    notifications=notifications,
                    verified=False,
                    retries=USERNAME_RETRIES,
                )
                if "pd_request" in web.input() and web.input().get("pd_program"):
                    web.setcookie("pda", web.input().get("pd_program"))
                return render['account/verify'](
                    username=f.username.value, email=f.email.value
                )
            except OLAuthenticationError as e:
                f.note = get_login_error(e.__str__())
                from openlibrary.plugins.openlibrary.sentry import sentry

                if sentry.enabled:
                    extra = {'response': e.response} if hasattr(e, 'response') else None
                    sentry.capture_exception(e, extras=extra)

        return render['account/create'](f, pd_options=get_pd_options())


del delegate.pages['/account/register']


def _set_account_cookies(ol_account: OpenLibraryAccount, expires: int | str) -> None:
    if ol_account.get_user().get_safe_mode() == 'yes':
        web.setcookie('sfw', 'yes', expires=expires)
    if 'yrg_banner_pref' in ol_account.get_user().preferences():
        web.setcookie(
            ol_account.get_user().preferences()['yrg_banner_pref'],
            '1',
            expires=(3600 * 24 * 365),
        )


class PDRequestStatus(Enum):
    REQUESTED = 0
    EMAILED = 1
    FULFILLED = 2


def _update_account_on_pd_request(ol_account: OpenLibraryAccount) -> None:
    pda = web.cookies().get("pda")
    ol_account.get_user().save_preferences(
        {
            "rpd": PDRequestStatus.REQUESTED.value,
            "pda": pda,
        }
    )


def _notify_on_rpd_verification(ol_account, org):
    if org:
        org = "vtmas_disabilityresources" if org == "unqualified" else org
        displayname = web.safestr(ol_account.displayname)
        msg = render_template(
            "email/account/pd_request", displayname=displayname, org=org
        )
        web.sendmail(
            config.from_address,
            ol_account.email,
            subject=msg.subject.strip(),
            message=msg,
        )
        ol_account.get_user().save_preferences(
            {
                "rpd": PDRequestStatus.EMAILED.value,
            }
        )


def _update_account_on_pd_fulfillment(ol_account: OpenLibraryAccount) -> None:
    ol_account.get_user().save_preferences({"rpd": PDRequestStatus.FULFILLED.value})


def _expire_pd_cookies():
    web.setcookie("pda", "", expires=1)


class account_login_json(delegate.page):
    encoding = "json"
    path = "/account/login"

    def POST(self):
        """Overrides `account_login` and infogami.login to prevent users from
        logging in with Open Library username and password if the
        payload is json. Instead, if login attempted w/ json
        credentials, requires Archive.org s3 keys.
        """

        d = json.loads(web.data())
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
            web.setcookie(config.login_cookie_name, web.ctx.conn.get_auth_token())
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

    def perform_post_login_action(self, i, ol_account):
        if i.action:
            op, args = i.action.split(":")
            if op == "follow" and args:
                publisher = args
                if publisher_account := OpenLibraryAccount.get_by_username(publisher):
                    PubSub.subscribe(
                        subscriber=ol_account.username, publisher=publisher
                    )

                    publisher_name = publisher_account["data"]["displayname"]
                    flash_message = f"You are now following {publisher_name}!"
                    return flash_message

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
        i = web.input(redirect=referer, action="")
        f = forms.Login()
        f['redirect'].value = i.redirect
        f['action'].value = i.action
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
            action="",
        )
        email = '' if (i.access and i.secret) else i.username
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
        email = email or audit.get('ia_email') or audit.get('ol_email')

        expires = 3600 * 24 * 365 if i.remember else ""
        web.setcookie('pd', int(audit.get('special_access')) or '', expires=expires)
        web.setcookie(
            config.login_cookie_name, web.ctx.conn.get_auth_token(), expires=expires
        )

        if ol_account := OpenLibraryAccount.get_by_email(email):
            _set_account_cookies(ol_account, expires)

            if web.cookies().get("pda"):
                _update_account_on_pd_request(ol_account)
                _notify_on_rpd_verification(
                    ol_account, get_pd_org(web.cookies().get("pda"))
                )
                _expire_pd_cookies()
                add_flash_message(
                    "info",
                    _(
                        "Thank you for registering an Open Library account and "
                        "requesting special print disability access. You should receive "
                        "an email detailing next steps in the process."
                    ),
                )

            has_special_access = audit.get('special_access')
            if (
                has_special_access
                and ol_account.get_user().preferences().get('pda', '')
                and ol_account.get_user().preferences().get('rpd')
                != PDRequestStatus.FULFILLED.value
            ):
                _update_account_on_pd_fulfillment(ol_account)

        blacklist = [
            "/account/login",
            "/account/create",
        ]

        # Processing post login action
        if flash_message := self.perform_post_login_action(i, ol_account):
            add_flash_message('note', _(flash_message))

        if i.redirect == "" or any(path in i.redirect for path in blacklist):
            i.redirect = "/account/books"
        stats.increment('ol.account.xauth.login')
        raise web.seeother(i.redirect)


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
        ol_account = OpenLibraryAccount.get_by_username(username)
        if ol_account:
            return _("Username unavailable")

        ia_account = account_validation.ia_username_exists(username)
        if ia_account:
            return _("Username unavailable")

    @staticmethod
    def validate_email(email):
        ol_account = OpenLibraryAccount.get_by_email(email)
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


class account_ia_email_forgot(delegate.page):
    path = "/account/email/forgot-ia"

    def GET(self):
        return render_template('account/email/forgot-ia')

    def POST(self):
        i = web.input(email='', password='')
        err = ""

        if valid_email(i.email):
            act = OpenLibraryAccount.get_by_email(i.email)
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


# Add a POST redirect for prefs from global filter
class account_preferences(delegate.page):
    path = "account/preferences"
    encoding = "json"

    def POST(self):
        d = json.loads(web.data())
        prefs = {
            'mode': d.get('mode', 'all'),
            'language': d.get('language', 'en'),
            'date': d.get('date', [1900, 2025]),
        }

        # Save to localStorage?

        expires = 3600 * 24 * 365
        web.setcookie('ol_mode', prefs['mode'], expires=expires)
        web.setcookie('ol_lang', prefs['language'], expires=expires)
        web.setcookie('ol_date', ",".join(map(str, prefs['date'])), expires=expires)

        if d.get('redirect', True):
            raise web.seeother("/account")
        else:
            return delegate.RawText(
                json.dumps({'status': 'ok'}), content_type="application/json"
            )


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


class PatronExportException(Exception):
    pass


class PatronExport(ABC):
    @staticmethod
    def make_export(data: list[dict], fieldnames: list[str]):
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in data:
            writer.writerow(row)

        csv_output = output.getvalue()
        output.close()

        return csv_output

    @staticmethod
    def get_work_from_id(work_id: str) -> "Work":
        """
        Gets work data for a given work ID (OLxxxxxW format), used to access work author, title, etc. for CSV generation.
        """
        # Can't put at top due to cyclical imports
        from openlibrary.plugins.upstream.models import Work

        work_key = f"/works/{work_id}"
        work: Work = web.ctx.site.get(work_key)
        if not work:
            raise ValueError(f"No Work found for {work_key}.")
        if work.type.key == '/type/redirect':
            # Resolve the redirect before exporting
            work = web.ctx.site.get(
                Work.resolve_redirect_chain(work_key).get('resolved_key')
            )
        return work

    @property
    def user(self) -> "User":
        if not (result := accounts.get_current_user()):
            raise PatronExportException("Must be logged in to export data.")
        return result

    @property
    def date_format(self):
        return '%Y-%m-%d %H:%M:%S'

    @property
    @abstractmethod
    def filename(self) -> str:
        pass

    @property
    @abstractmethod
    def fieldnames(self) -> list[str]:
        pass

    @abstractmethod
    def get_data(self) -> list:
        pass


class ReadingLogExport(PatronExport):

    @property
    def filename(self) -> str:
        return 'OpenLibrary_ReadingLog.csv'

    @property
    def fieldnames(self) -> list[str]:
        return [
            "Work ID",
            "Title",
            "Authors",
            "First Publish Year",
            "Edition ID",
            "Edition Count",
            "Bookshelf",
            "My Ratings",
            "Ratings Average",
            "Ratings Count",
            "Has Ebook",
            "Subjects",
            "Subject People",
            "Subject Places",
            "Subject Times",
        ]

    def get_data(self) -> list:
        def get_subjects(
            work: "Work",
            subject_type: SubjectType = "subject",
        ) -> str:
            return " | ".join(s.title for s in work.get_subject_links(subject_type))

        bookshelf_map = {1: 'Want to Read', 2: 'Currently Reading', 3: 'Already Read'}
        username = self.user.key.split('/')[-1]
        books = Bookshelves.iterate_users_logged_books(username)
        result = []
        for book in books:
            work_id = f"OL{book['work_id']}W"
            if edition_id := book.get("edition_id", ""):
                edition_id = f"OL{edition_id}M"

            work = self.get_work_from_id(work_id)
            if work.type.key == '/type/delete':
                continue

            ratings = work.get_rating_stats() or {"average": "", "count": ""}
            ratings_average, ratings_count = ratings.values()
            result.append(
                {
                    "Work ID": work_id,
                    "Title": work.title,
                    "Authors": " | ".join(work.get_author_names()),
                    "First Publish Year": work.first_publish_year,
                    "Edition ID": edition_id,
                    "Edition Count": work.edition_count,
                    "Bookshelf": bookshelf_map[work.get_users_read_status(username)],
                    "My Ratings": work.get_users_rating(username) or "",
                    "Ratings Average": ratings_average,
                    "Ratings Count": ratings_count,
                    "Has Ebook": work.has_ebook(),
                    "Subjects": get_subjects(work=work, subject_type="subject"),
                    "Subject People": get_subjects(work=work, subject_type="person"),
                    "Subject Places": get_subjects(work=work, subject_type="place"),
                    "Subject Times": get_subjects(work=work, subject_type="time"),
                }
            )

        return result


class BookNoteExport(PatronExport):

    @property
    def filename(self) -> str:
        return 'OpenLibrary_BookNotes.csv'

    @property
    def fieldnames(self) -> list[str]:
        return [
            "Work ID",
            "Edition ID",
            "Note",
            "Created On",
        ]

    def get_data(self) -> list:
        username = self.user.key.split('/')[-1]
        notes = Booknotes.select_all_by_username(username)
        result = []
        for note in notes:
            result.append(
                {
                    "Work ID": f"OL{note['work_id']}W",
                    "Edition ID": f"OL{note['edition_id']}M",
                    "Note": note["notes"],
                    "Created On": note['created'].strftime(self.date_format),
                }
            )
        return result


class ReviewExport(PatronExport):

    @property
    def filename(self) -> str:
        return 'OpenLibrary_Reviews.csv'

    @property
    def fieldnames(self) -> list[str]:
        return [
            "Work ID",
            "Review Category",
            "Review Value",
            "Created On",
        ]

    def get_data(self) -> list:
        username = self.user.key.split('/')[-1]
        observations = Observations.select_all_by_username(username)
        result = []
        for o in observations:
            result.append(
                {
                    "Work ID": f"OL{o['work_id']}W",
                    "Review Category": o["observation_type"],
                    "Review Value": o["observation_value"],
                    "Created On": o["created"].strftime(self.date_format),
                }
            )
        return result


class ListExport(PatronExport):

    @property
    def filename(self) -> str:
        return 'Openlibrary_ListOverview.csv'

    @property
    def fieldnames(self) -> list[str]:
        return [
            "List ID",
            "List Name",
            "List Description",
            "Entry",
            "Created On",
            "Last Updated",
        ]

    def get_data(self) -> list:
        result = []
        with elapsed_time("user.get_lists()"):
            lists = self.user.get_lists(limit=1000)
        with elapsed_time("generate_list_overview()"):
            for li in lists:
                last_updated = li.last_modified or ""
                if isinstance(last_updated, datetime):
                    last_updated = last_updated.strftime(self.date_format)
                for seed in li.seeds:
                    result.append(
                        {
                            "List ID": li.key.split("/")[-1],
                            "List Name": li.name or "",
                            "List Description": li.description or "",
                            "Entry": seed if isinstance(seed, str) else seed.key,
                            "Created On": li.created.strftime(self.date_format),
                            "Last Updated": last_updated,
                        }
                    )
        return result


class RatingExport(PatronExport):

    @property
    def filename(self) -> str:
        return 'OpenLibrary_Ratings.csv'

    @property
    def fieldnames(self) -> list[str]:
        return [
            "Work ID",
            "Edition ID",
            "Title",
            "Author(s)",
            "Rating",
            "Created On",
        ]

    def get_data(self) -> list:
        username = self.user.key.split('/')[-1]
        ratings = Ratings.select_all_by_username(username)
        result = []
        for rating in ratings:
            work_id = f"OL{rating['work_id']}W"
            if edition_id := rating.get("edition_id", ""):
                edition_id = f"OL{edition_id}M"
            work = self.get_work_from_id(work_id)
            result.append(
                {
                    "Work ID": work_id,
                    "Edition ID": edition_id,
                    "Title": work.title,
                    "Author(s)": " | ".join(work.get_author_names()),
                    "Rating": rating["rating"],
                    "Created On": rating["created"].strftime(self.date_format),
                }
            )
        return result


class export_books(delegate.page):
    path = "/account/export"

    @require_login
    def GET(self):
        i = web.input(type='')

        export = self.get_export(i.type)
        data = export.make_export(export.get_data(), export.fieldnames)

        web.header('Content-Type', 'text/csv')
        web.header('Content-disposition', f'attachment; filename={export.filename}')
        return delegate.RawText(data, content_type="text/csv")

    def get_export(self, export_type: str) -> PatronExport:
        export: PatronExport | None = None

        match export_type:
            case "reading_log":
                export = ReadingLogExport()
            case "book_notes":
                export = BookNoteExport()
            case "reviews":
                export = ReviewExport()
            case "lists":
                export = ListExport()
            case "ratings":
                export = RatingExport()
            case _:
                raise KeyError("Unrecognized export type")

        return export


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


class account_anonymization_json(delegate.page):
    path = "/account/anonymize"
    encoding = "json"

    def POST(self):
        i = web.input(test='false')
        test = i.test == "true"

        # Get S3 keys from request header
        try:
            s3_access, s3_secret = self._parse_auth_header()
        except ValueError:
            raise web.HTTPError("400 Bad Request", {"Content-Type": "application/json"})

        # Fetch and anonymize account
        xauthn_response = InternetArchiveAccount.s3auth(s3_access, s3_secret)
        if 'error' in xauthn_response:
            raise web.HTTPError("404 Not Found", {"Content-Type": "application/json"})

        ol_account = OpenLibraryAccount.get_by_link(xauthn_response.get('itemname', ''))
        if not ol_account:
            raise web.HTTPError("404 Not Found", {"Content-Type": "application/json"})

        try:
            with RunAs(ol_account.username):
                result = ol_account.anonymize(test=test)
        except Exception as e:
            logger.error(e)
            raise web.HTTPError(
                "500 Internal Server Error", {"Content-Type": "application/json"}
            )

        raise web.HTTPError(
            "200 OK", {"Content-Type": "application/json"}, data=json.dumps(result)
        )

    def _parse_auth_header(self):
        header_value = web.ctx.env.get("HTTP_AUTHORIZATION", "")
        try:
            _, keys = header_value.split('LOW ', 1)
            s3_access, s3_secret = keys.split(':', 1)
            return s3_access.strip(), s3_secret.strip()
        except ValueError:
            raise ValueError("Malformed Authorization Header")


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
    if not (account := OpenLibraryAccount.get_by_username(mb.username)):
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
    # loan. No apparently way to distinguish between current and past loans with
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
