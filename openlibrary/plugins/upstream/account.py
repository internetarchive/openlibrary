from typing import Any, Callable, Iterable, Mapping
import web
import logging
import json
import re

from infogami.utils import delegate
from infogami import config
from infogami.utils.view import (
    require_login,
    render,
    render_template,
    add_flash_message,
)

from infogami.infobase.client import ClientException
from infogami.utils.context import context
import infogami.core.code as core

from openlibrary import accounts
from openlibrary.i18n import gettext as _
from openlibrary.core import helpers as h, lending
from openlibrary.core.booknotes import Booknotes
from openlibrary.core.bookshelves import Bookshelves
from openlibrary.core.observations import Observations
from openlibrary.core.ratings import Ratings
from openlibrary.plugins.recaptcha import recaptcha
from openlibrary.plugins.upstream.mybooks import MyBooksTemplate
from openlibrary.plugins import openlibrary as olib
from openlibrary.accounts import (
    audit_accounts,
    Account,
    OpenLibraryAccount,
    InternetArchiveAccount,
    valid_email,
)
from openlibrary.plugins.upstream import borrow, forms, utils

import urllib


logger = logging.getLogger("openlibrary.account")

USERNAME_RETRIES = 3

# XXX: These need to be cleaned up
send_verification_email = accounts.send_verification_email
create_link_doc = accounts.create_link_doc
sendmail = accounts.sendmail

LOGIN_ERRORS = {
    "invalid_email": "The email address you entered is invalid",
    "account_blocked": "This account has been blocked",
    "account_locked": "This account has been blocked",
    "account_not_found": "No account was found with this email. Please try again",
    "account_incorrect_password": "The password you entered is incorrect. Please try again",
    "account_bad_password": "Wrong password. Please try again",
    "account_not_verified": "Please verify your Open Library account before logging in",
    "ia_account_not_verified": "Please verify your Internet Archive account before logging in",
    "missing_fields": "Please fill out all fields and try again",
    "email_registered": "This email is already registered",
    "username_registered": "This username is already registered",
    "ia_login_only": "Sorry, you must use your Internet Archive email and password to log in",
    "max_retries_exceeded": "A problem occurred and we were unable to log you in.",
    "invalid_s3keys": "Login attempted with invalid Internet Archive s3 credentials.",
    "wrong_ia_account": "An Open Library account with this email is already linked to a different Internet Archive account. Please contact info@openlibrary.org.",
}


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
                    raise ValueError(
                        'Invalid Open Library account email ' 'or itemname'
                    )
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

    def get_form(self):
        """
        :rtype: forms.RegisterForm
        """
        f = forms.Register()
        recap = self.get_recap()
        f.has_recaptcha = recap is not None
        if f.has_recaptcha:
            f.inputs = list(f.inputs) + [recap]
        return f

    def get_recap(self):
        if self.is_plugin_enabled('recaptcha'):
            public_key = config.plugin_recaptcha.public_key
            private_key = config.plugin_recaptcha.private_key
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
            except ValueError:
                f.note = LOGIN_ERRORS['max_retries_exceeded']

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
        from openlibrary.plugins.openlibrary.code import BadRequest

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
                raise olib.code.BadRequest(error)
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
    * account_not_verified: Error page is dispalyed with button to "resend verification email".
    """

    path = "/account/login"

    def render_error(self, error_key, i):
        f = forms.Login()
        f.fill(i)
        f.note = LOGIN_ERRORS[error_key]
        return render.login(f)

    def GET(self):
        referer = web.ctx.env.get('HTTP_REFERER', '')
        # Don't set referer if request is from offsite
        if ('openlibrary.org' not in referer
            or referer.endswith('openlibrary.org/')):
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
        error = audit.get('error')
        if error:
            return self.render_error(error, i)

        expires = 3600 * 24 * 365 if i.remember else ""
        web.setcookie('pd', int(audit.get('special_access')) or '', expires=expires)
        web.setcookie(
            config.login_cookie_name, web.ctx.conn.get_auth_token(), expires=expires
        )
        blacklist = [
            "/account/login",
            "/account/create",
        ]
        if i.redirect == "" or any([path in i.redirect for path in blacklist]):
            i.redirect = "/account/loans"
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


class account_verify(delegate.page):
    """Verify user account."""

    path = "/account/verify/([0-9a-f]*)"

    def GET(self, code):
        docs = web.ctx.site.store.values(type="account-link", name="code", value=code)
        if docs:
            doc = docs[0]

            account = accounts.find(username=doc['username'])
            if account:
                if account['status'] != "pending":
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
    def validate_username(username):
        if not 3 <= len(username) <= 20:
            return _('Username must be between 3-20 characters')
        if not re.match('^[A-Za-z0-9-_]{3,20}$', username):
            return _('Username may only contain numbers and letters')
        ol_account = OpenLibraryAccount.get(username=username)
        if ol_account:
            return _("Username unavailable")

    @staticmethod
    def validate_email(email):
        if not (email and re.match(r'.*@.*\..*', email)):
            return _('Must be a valid email address')

        ol_account = OpenLibraryAccount.get(email=email)
        if ol_account:
            return _('Email already registered')

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
        link = accounts.get_link(code)
        if link:
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


class account_ol_email_forgot(delegate.page):
    path = "/account/email/forgot"

    def GET(self):
        return render_template('account/email/forgot')

    def POST(self):
        i = web.input(username='', password='')
        err = ""
        act = OpenLibraryAccount.get(username=i.username)

        if act:
            if OpenLibraryAccount.authenticate(act.email, i.password) == "ok":
                return render_template('account/email/forgot', email=act.email)
            else:
                err = "Incorrect password"

        elif valid_email(i.username):
            err = "Please enter a username, not an email"

        else:
            err = "Sorry, this user does not exist"

        return render_template('account/email/forgot', err=err)


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
        user = accounts.get_current_user()
        user.save_preferences(web.input())
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
        raise web.seeother('/people/%s/books' % (username))


# This would be by the civi backend which would require the api keys
class fake_civi(delegate.page):
    path = "/internal/fake/civicrm"

    def GET(self):
        i = web.input(entity='Contact')
        contact = {'values': [{'contact_id': '270430'}]}
        contributions = {
            'values': [
                {
                    "receive_date": "2019-07-31 08:57:00",
                    "custom_52": "9780062457714",
                    "total_amount": "50.00",
                    "custom_53": "ol",
                    "contact_id": "270430",
                    "contribution_status": "",
                }
            ]
        }
        entity = contributions if i.entity == 'Contribution' else contact
        return delegate.RawText(json.dumps(entity), content_type="application/json")


class import_books(delegate.page):
    path = "/account/import"

    @require_login
    def GET(self):
        user = accounts.get_current_user()
        username = user['key'].split('/')[-1]

        return MyBooksTemplate(username, 'imports').render()


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


def csv_string(source: Iterable[Mapping], row_formatter: Callable = None) -> str:
    """
    Given an list of dicts, generate comma separated values where each dict is a row.
    An optional reformatter function can be provided to transform or enrich each dict.
    The order and names of the formatter's the output dict keys will determine the
    order and header column titles of the resulting csv string.
    :param source: An iterable of all the rows that should appear in the csv string.
    :param formatter: A Callable that accepts a Mapping and returns a dict.
    >>> csv = csv_string([{"row_id": x, "t w o": 2, "upper": x.upper()} for x in "ab"])
    >>> csv.splitlines()
    ['Row ID,T W O,Upper', 'a,2,A', 'b,2,B']
    """
    if not row_formatter:  # The default formatter reuses the inbound dict unmodified

        def row_formatter(row: dict) -> dict:
            return row

    def csv_body() -> Iterable[str]:
        """
        On the first row, use csv_header_and_format() to get and yield the csv_header.
        Then use csv_format to yield each row as a string of comma separated values.
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
            data = self.generate_list_overview(user.get_lists(limit=1000))
            filename = 'Openlibrary_ListOverview.csv'
        elif i.type == 'ratings':
            data = self.generate_star_ratings(username)
            filename = 'OpenLibrary_Ratings.csv'

        web.header('Content-Type', 'text/csv')
        web.header('Content-disposition', f'attachment; filename={filename}')
        return delegate.RawText('' or data, content_type="text/csv")

    def generate_reading_log(self, username):
        books = Bookshelves.get_users_logged_books(username, limit=10000)
        csv = []
        csv.append('Work Id,Edition Id,Bookshelf\n')
        mapping = {1: 'Want to Read', 2: 'Currently Reading', 3: 'Already Read'}
        for book in books:
            row = [
                'OL{}W'.format(book['work_id']),
                'OL{}M'.format(book['edition_id']) if book['edition_id'] else '',
                '{}\n'.format(mapping[book['bookshelf_id']]),
            ]
            csv.append(','.join(row))
        return ''.join(csv)

    def generate_book_notes(self, username: str) -> str:
        def format_booknote(booknote: Mapping) -> dict:
            escaped_note = booknote['notes'].replace('"', '""')
            return {
                "work_id": f"OL{booknote['work_id']}W",
                "edition_id": f"OL{booknote['edition_id']}M",
                "note":  f'"{escaped_note}"',
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
        csv = []
        csv.append('List ID,List Name,List Description,Entry,Created On,Last Updated')

        for list in lists:
            list_id = list.key.split('/')[-1]
            created_on = list.created.strftime(self.date_format)
            last_updated = list.last_modified.strftime(self.date_format) if list.last_modified else ''
            for seed in list.seeds:
                entry = seed
                if not isinstance(seed, str):
                    entry = seed.key
                list_name = list.name.replace('"', '""') if list.name else ''
                list_desc = list.description.replace('"', '""') if list.description else ''
                row = [
                    list_id,
                    f'"{list_name}"',
                    f'"{list_desc}"',
                    entry,
                    created_on,
                    last_updated
                ]
                csv.append(','.join(row))

        return '\n'.join(csv)

    def generate_star_ratings(self, username: str) -> str:
        def format_rating(rating: Mapping) -> dict:
            if edition_id := rating.get("edition_id") or "":
                edition_id = f"OL{edition_id}M"
            return {
                "Work ID": f"OL{rating['work_id']}W",
                "Edition ID": edition_id,
                "Rating": f"{rating['rating']}",
                "Created On": rating['created'].strftime(self.date_format),
            }

        return csv_string(Ratings.select_all_by_username(username), format_rating)


class account_loans(delegate.page):
    path = "/account/loans"

    @require_login
    def GET(self):
        user = accounts.get_current_user()
        user.update_loan_status()
        username = user['key'].split('/')[-1]

        return MyBooksTemplate(username, 'loans').render()


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


class account_waitlist(delegate.page):
    path = "/account/waitlist"

    def GET(self):
        raise web.seeother("/account/loans")

# Disabling be cause it prevents account_my_books_redirect from working
# for some reason. The purpose of this class is to not show the "Create" link for
# /account pages since that doesn't make any sense.
# class account_others(delegate.page):
#     path = "(/account/.*)"
#
#     def GET(self, path):
#         return render.notfound(path, create=False)


def send_forgot_password_email(username, email):
    key = "account/%s/password" % username

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
