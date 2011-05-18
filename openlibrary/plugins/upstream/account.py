import web
import hmac
import random
import urllib

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

def _generate_salted_hash(key, text, salt=None):
    salt = salt or hmac.HMAC(key, str(random.random())).hexdigest()[:5]
    hash = hmac.HMAC(key, salt + web.utf8(text)).hexdigest()
    return '%s$%s' % (salt, hash)

    
def _verify_salted_hash(key, text, hash):
    salt = hash.split('$', 1)[0]
    return _generate_salted_hash(key, text, salt) == hash


def get_secret_key():    
    return config.infobase['secret_key']


def sendmail(to, msg, cc=None):
    cc = cc or []
    if config.get('dummy_sendmail'):
        print >> web.debug, 'To:', to
        print >> web.debug, 'From:', config.from_address
        print >> web.debug, 'Subject:', msg.subject
        print >> web.debug
        print >> web.debug, web.safestr(msg)
    else:
        web.sendmail(config.from_address, to, subject=msg.subject.strip(), message=web.safestr(msg), cc=cc)
    

def as_admin(f):
    """Infobase allows some requests only from admin user. This decorator logs in as admin, executes the function and clears the admin credentials."""
    def g(*a, **kw):
        try:
            delegate.admin_login()
            return f(*a, **kw)
        finally:
            web.ctx.headers = []
    return g


@as_admin
def get_user_code(email):
    return web.ctx.site.get_reset_code(email)


@as_admin
def get_user_email(username):
    return web.ctx.site.get_user_email(username).email


@as_admin
def reset_password(username, code, password):
    return web.ctx.site.reset_password(username, code, password)
    

class account(delegate.page):
    @require_login
    def GET(self):
        user = web.ctx.site.get_user()
        return render.account(user)

class account_login(delegate.page):
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
        if web.ctx.site.get('/people/' + i.username) is None:
            return self.error('account_user_notfound', i)
        
        try:
            web.ctx.site.login(i.username, i.password, i.remember)
        except ClientException, e:
            code = e.get_data().get("code")
            if code == "email_not_verified":
                email = get_user_email("/people/" + i.username)
                return render_template("account/not_verified", username=i.username, password=i.password, email=email)
            else:
                return self.error("account_incorrect_password", i)

        if i.redirect == "/account/login" or i.redirect == "":
            i.redirect = "/"

        expires = (i.remember and 3600*24*7) or ""
        web.setcookie(config.login_cookie_name, web.ctx.conn.get_auth_token(), expires=expires)
        raise web.seeother(i.redirect)

    def POST_resend_verification_email(self, i):
        try:
            web.ctx.site.login(i.username, i.password, i.remember)
        except ClientException, e:
            code = e.get_data().get("code")
            if code != "email_not_verified":
                return self.error("account_incorrect_password", i)

        email = get_user_email("/people/" + i.username)
        account_create().send_verification_email(i.username, email)

        user = web.ctx.site.get('/people/' + i.username)
        title = _("Hi %(user)s", user=user.displayname or i.username)
        message = _("We've sent the verification email to %(email)s. You'll need to read that and click on the verification link to verify your email.", email=email)
        return render.message(title, message)

class account_create(delegate.page):
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
            web.ctx.site.register(i.username, i.displayname, i.email, i.password)
        except ClientException, e:
            f.note = str(e)
            return render['account/create'](f)

        self.send_verification_email(i.username, i.email)
        return render['account/verify'](username=i.username, email=i.email)
        
    def send_verification_email(self, username, email):
        code = _generate_salted_hash(get_secret_key(), username + ',' + email)
        link = web.ctx.home + "/account/verify?" + urllib.urlencode({'username': username, 'email': email, 'code': code})
        
        msg = render['email/account/verify'](username=username, email=email, password=None, link=link)
        sendmail(email, msg)
        
del delegate.pages['/account/register']
    

class account_verify(delegate.page):
    path = "/account/verify"
    def GET(self):
        i = web.input(username="", email="", code="")
        verified = _verify_salted_hash(get_secret_key(), i.username + ',' + i.email, i.code)
        
        if verified:
            web.ctx.site.update_user_details(i.username, verified=True)
            user = web.ctx.site.get("/people/" + i.username)
            return render['account/verify/success'](user.displayname or i.username)
        else:
            return render['account/verify/failed']()


class account_email(delegate.page):
    path = "/account/email"
    
    def get_email(self):
        return context.user.email
        
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
            
            code = _generate_salted_hash(get_secret_key(), username + ',' + i.email)
            link = web.ctx.home + '/account/email/verify' + '?' + urllib.urlencode({"username": username, 'email': i.email, 'code': code})

            msg = render['email/email/verify'](username=username, email=i.email, link=link)
            sendmail(i.email, msg)
            
            title = _("Hi %(user)s", user=user.displayname or username)
            message = _("We've sent an email to %(email)s. You'll need to read that and click on the verification link to update your email.", email=i.email)
            return render.message(title, message)


class account_email_verify(delegate.page):
    path = "/account/email/verify"
    
    def GET(self):
        i = web.input(username='', email='', code='')
        
        verified = _verify_salted_hash(get_secret_key(), i.username + ',' + i.email, i.code)
        if verified:
            if web.ctx.site.find_user_by_email(i.email) is not None:
                title = _("Email address is already used.")
                message = _("Your email address couldn't be updated. The specified email address is already used.")
            else:
                web.ctx.site.update_user_details(i.username, email=i.email)
                title = _("Email verification successful.")
                message = _('Your email address has been successfully verified and updated in your account.')
        else:
            title = _("Email address couldn't be verified.")
            message = _("Your email address couldn't be verified. The verification link seems invalid.")
            
        return render.message(title, message)
    

class account_delete(delegate.page):
    path = "/account/delete"
    @require_login
    def GET(self):
        return render['account/delete']()
    
    @require_login
    def POST(self):
        return "Not yet implemented"


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

        try:
            user = web.ctx.site.update_user(i.password, i.new_password, None)
        except ClientException, e:
            f.note = str(e)
            return render['account/password'](f)
            
        add_flash_message('note', _('Your password has been updated successfully.'))
        web.seeother('/')
        

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
        
        d = get_user_code(i.email)
        
        link = web.ctx.home + '/account/password/reset' + '?' + urllib.urlencode({'code': d.code, 'username': d.username})
        
        msg = render['email/password/reminder'](d.username, link)
        sendmail(i.email, msg)
        
        return render['account/password/sent'](i.email)


class account_password_reset(delegate.page):
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
            
        try:
            reset_password(i.username, i.code, i.password)
            web.ctx.site.login(i.username, i.password, False)
            add_flash_message('info', _("Your password has been updated successfully."))
            raise web.seeother('/')
        except Exception, e:
            add_flash_message('error', "Failed to reset password.<br/><br/> Reason: "  + str(e))
            return self.GET()


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
        print "account_others", path
        return render.notfound(path, create=False)

class user_preferences(delegate.page):
    path = "(/people/[^/]*/preferences)"
    
    def GET(self, path):
        print 'user_preferences', path, web.ctx.site.can_write(path), context.user
        # only people who can modify the preferences should be able to see them
        if web.ctx.site.can_write(path):
            return core.view().GET(path)
        else:
            return render.permission_denied(path, "Permission Denied.")
