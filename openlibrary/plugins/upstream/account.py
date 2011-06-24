import web
import hmac
import logging
import random
import urllib
import uuid
import datetime, time

from infogami.utils import delegate
from infogami import config
from infogami.utils.view import require_login, render, render_template, add_flash_message
from infogami.infobase.client import ClientException
from infogami.utils.context import context
import infogami.core.code as core

from openlibrary.i18n import gettext as _
import forms
import utils
import borrow

logger = logging.getLogger("openlibrary.account")

class Account(web.storage):
    
    @property
    def username(self):
        return self._key.split("/")[-1]
        
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
        
    def verify_password(self, password):
        return verify_hash(get_secret_key(), password, self.enc_password)
        
    def update_password(self, new_password):
        web.ctx.site.update_account(self.username, password=new_password)
    
    def update_email(self, email):
        web.ctx.site.update_account(self.username, email=email)
    
    @staticmethod
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
            doc = query("email", email)
        else:
            doc = None
            
        return doc and Account(doc)

class account(delegate.page):
    """Account preferences.
    """
    @require_login
    def GET(self):
        user = web.ctx.site.get_user()
        return render.account(user)

class account_create(delegate.page):
    """New account creation.

    Account will in the pending state until the email is activated.
    """
    path = "/account/create"

    def GET(self):
        f = forms.Register()
        return render['account/create'](f)

    def POST(self):
        i = web.input('email', 'password', 'username', agreement="no")
        i.displayname = i.get('displayname') or i.username
        
        f = forms.Register()
        
        if not f.validates(i):
            return render['account/create'](f)

        if i.agreement != "yes":
            f.note = utils.get_error("account_create_tos_not_selected")
            return render['account/create'](f)

        try:
            web.ctx.site.register(
                username=i.username,
                email=i.email,
                password=i.password,
                displayname=i.displayname)
        except ClientException, e:
            f.note = str(e)
            return render['account/create'](f)

        send_verification_email(i.username, i.email)
        return render['account/verify'](username=i.username, email=i.email)

del delegate.pages['/account/register']

class account_login(delegate.page):
    """Account login.

    Login can fail because of the following reasons:

    * account_not_found: Error message is displayed.
    * account_bad_password: Error message is displayed with a link to reset password.
    * account_not_verified: Error page is dispalyed with button to "resend verification email".
    """
    path = "/account/login"

    def GET(self):
        referer = web.ctx.env.get('HTTP_REFERER', '/')
        i = web.input(redirect=referer)
        f = forms.Login()
        f['redirect'].value = i.redirect
        return render.login(f)

    def POST(self):
        i = web.input(remember=False, redirect='/', action="login")
        
        if i.action == "resend_verification_email":
            return self.POST_resend_verification_email(i)
        else:
            return self.POST_login(i)

    def error(self, name, i):
        f = forms.Login()
        f.fill(i)
        f.note = utils.get_error(name)
        return render.login(f)

    def POST_login(self, i):
        try:
            web.ctx.site.login(i.username, i.password)
        except ClientException, e:
            code = e.get_data().get("code")

            logger.error("login failed for %s with error code %s", i.username, code)

            if code == "account_not_verified":
                account = Account.find(username=i.username)
                return render_template("account/not_verified", username=i.username, password=i.password, email=account.email)
            else:
                return self.error("account_incorrect_password", i)

        if i.redirect == "/account/login" or i.redirect == "":
            i.redirect = "/"

        expires = (i.remember and 3600*24*7) or ""
        web.setcookie(config.login_cookie_name, web.ctx.conn.get_auth_token(), expires=expires)
        raise web.seeother(i.redirect)

    def POST_resend_verification_email(self, i):
        try:
            web.ctx.site.login(i.username, i.password)
        except ClientException, e:
            code = e.get_data().get("code")
            if code != "account_not_verified":
                return self.error("account_incorrect_password", i)

        account = Account.find(username=i.username)
        send_verification_email(i.username, account.email)

        title = _("Hi %(user)s", user=account.displayname)
        message = _("We've sent the verification email to %(email)s. You'll need to read that and click on the verification link to verify your email.", email=account.email)
        return render.message(title, message)

class account_verify(delegate.page):
    """Verify user account.
    """
    path = "/account/verify/([0-9a-f]*)"

    def GET(self, code):
        docs = web.ctx.site.store.values(type="account-link", name="code", value=code)
        if docs:
            doc = docs[0]

            account = Account.find(username = doc['username'])
            if account:
                if account['status'] != "pending":
                    return render['account/verify/activated']()
            web.ctx.site.activate_account(username=doc['username'])
            user = web.ctx.site.get("/people/" + doc['username'])
            return render['account/verify/success'](user.displayname or doc['username'])
        else:
            return render['account/verify/failed']()

class account_verify_old(delegate.page):
    """Old account verification code.

    This takes username, email and code as url parameters. The new one takes just the code as part of the url.
    """
    path = "/account/verify"
    def GET(self):
        i = web.input(username="", email="", code="")
        verified = verify_hash(get_secret_key(), i.username + ',' + i.email, i.code)

        if verified:
            web.ctx.site.activate_account(i.username)
            user = web.ctx.site.get("/people/" + i.username)
            return render['account/verify/success'](user.displayname or i.username)
        else:
            return render['account/verify/failed']()

class account_email(delegate.page):
    """Change email.
    """
    path = "/account/email"

    def get_email(self):
        return context.user.get_account()['email']

    @require_login
    def GET(self):
        f = forms.ChangeEmail()
        return render['account/email'](self.get_email(), f)

    @require_login
    def POST(self):
        f = forms.ChangeEmail()
        i = web.input()

        if not f.validates(i):
            return render['account/email'](self.get_email(), f)
        else:
            user = web.ctx.site.get_user()
            username = user.key.split('/')[-1]

            displayname = user.displayname or username

            send_email_change_email(username, i.email)

            title = _("Hi %(user)s", user=user.displayname or username)
            message = _("We've sent an email to %(email)s. You'll need to read that and click on the verification link to update your email.", email=i.email)
            return render.message(title, message)

class account_email_verify(delegate.page):
    path = "/account/email/verify/([0-9a-f]*)"

    def GET(self, code):
        docs = web.ctx.site.store.values(type="account-link", name="code", value=code)
        if docs:
            doc = docs[0]
            username = doc['username']
            email = doc['email']
            response = self.update_email(username, email)
            # Delete the link doc
            del web.ctx.site.store[doc['_key']]
            return response
        else:
            return self.bad_link()
        
    def update_email(self, username, email):
        if Account.find(email=email):
            title = _("Email address is already used.")
            message = _("Your email address couldn't be updated. The specified email address is already used.")
        else:
            logger.info("updated email of %s to %s", username, email)
            web.ctx.site.update_account(username=username, email=email, status="active")
            title = _("Email verification successful.")
            message = _('Your email address has been successfully verified and updated in your account.')
        return render.message(title, message)
        
    def bad_link(self):
        title = _("Email address couldn't be verified.")
        message = _("Your email address couldn't be verified. The verification link seems invalid.")
        return render.message(title, message)

class account_email_verify_old(account_email_verify):
    path = "/account/email/verify"

    def GET(self):
        i = web.input(username='', email='', code='')

        verified = verify_hash(get_secret_key(), i.username + ',' + i.email, i.code)
        if verified:
            return self.update_email(i.username, i.email)
        else:
            return self.bad_link()

class account_password(delegate.page):
    path = "/account/password"

    @require_login
    def GET(self):
        f = forms.ChangePassword()
        return render['account/password'](f)

    @require_login
    def POST(self):
        f = forms.ChangePassword()
        i = web.input()

        if not f.validates(i):
            return render['account/password'](f)
            
        user = web.ctx.site.get_user()
        username = user.key.split("/")[-1]
        
        if self.try_login(username, i.password):
            web.ctx.site.update_account(username, password=i.new_password)
            add_flash_message('note', _('Your password has been updated successfully.'))
            raise web.seeother('/account')
        else:
            f.note = "Invalid password"
            return render['account/password'](f)
        
    def try_login(self, username, password):
        account = Account.find(username=username)
        return account and account.verify_password(password)

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

        account = Account.find(email=i.email)
        
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
        docs = web.ctx.site.store.values(type="account-link", name="code", value=code)
        if not docs:
            title = _("Password reset failed.")
            message = "The password reset link seems invalid or expired."
            return render.message(title, message)

        doc = docs[0]
        username = doc['username']
        i = web.input()
        
        web.ctx.site.update_account(username, password=i.password)
        del web.ctx.site.store[doc['_key']]
        return render_template("account/password/reset_success", username=username)
        
class account_password_reset_old(delegate.page):
    path = "/account/password/reset"

    def GET(self):
        i = web.input(username='', code='')

        try:
            web.ctx.site.check_reset_code(i.username, i.code)
        except ClientException, e:
            title = _("Password reset failed.")
            message = web.safestr(e)
            return render.message(title, message)

        f = forms.ResetPassword()
        return render['account/password/reset'](f)

    def POST(self):
        i = web.input(username='', code='')

        try:
            web.ctx.site.check_reset_code(i.username, i.code)
        except ClientException, e:
            title = _("Password reset failed.")
            message = web.safestr(e)
            return render.message(title, message)

        f = forms.ResetPassword()

        if not f.validates(i):
            return render['account/password/reset'](f)

        web.ctx.site.update_account(i.username, password=i.password)
        add_flash_message('info', _("Your password has been updated successfully."))
        raise web.seeother('/account/login')

class account_notifications(delegate.page):
    path = "/account/notifications"

    @require_login
    def GET(self):
        prefs = web.ctx.site.get(context.user.key + "/preferences")
        d = (prefs and prefs.get('notifications')) or {}
        email = context.user.email
        return render['account/notifications'](d, email)

    @require_login
    def POST(self):
        key = context.user.key + '/preferences'
        prefs = web.ctx.site.get(key)

        d = (prefs and prefs.dict()) or {'key': key, 'type': {'key': '/type/object'}}

        d['notifications'] = web.input()

        web.ctx.site.save(d, 'save notifications')

        add_flash_message('note', _("Notification preferences have been updated successfully."))
        web.seeother("/account")

class account_loans(delegate.page):
    path = "/account/loans"

    @require_login
    def GET(self):
        user = web.ctx.site.get_user()
        user.update_loan_status()
        loans = borrow.get_loans(user)
        return render['account/borrow'](user, loans)

class account_others(delegate.page):
    path = "(/account/.*)"

    def GET(self, path):
        return render.notfound(path, create=False)


####

def send_verification_email(username, email):
    """Sends account verification email.
    """
    key = "account/%s/verify" % username

    doc = create_link_doc(key, username, email)
    web.ctx.site.store[key] = doc

    link = web.ctx.home + "/account/verify/" + doc['code']
    msg = render_template("email/account/verify", username=username, email=email, password=None, link=link)
    sendmail(email, msg)

def send_email_change_email(username, email):
    key = "account/%s/email" % username

    doc = create_link_doc(key, username, email)
    web.ctx.site.store[key] = doc

    link = web.ctx.home + "/account/email/verify/" + doc['code']
    msg = render_template("email/email/verify", username=username, email=email, link=link)
    sendmail(email, msg)

def send_forgot_password_email(username, email):
    key = "account/%s/password" % username

    doc = create_link_doc(key, username, email)
    web.ctx.site.store[key] = doc

    link = web.ctx.home + "/account/password/reset/" + doc['code']
    msg = render_template("email/password/reminder", username=username, link=link)
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
        logger.info("sending mail" + message)
    else:
        web.sendmail(config.from_address, to, subject=msg.subject.strip(), message=web.safestr(msg), cc=cc)

def generate_uuid():
    return str(uuid.uuid4()).replace("-", "")

def as_admin(f):
    """Infobase allows some requests only from admin user. This decorator logs in as admin, executes the function and clears the admin credentials."""
    def g(*a, **kw):
        try:
            delegate.admin_login()
            return f(*a, **kw)
        finally:
            web.ctx.headers = []
    return g
