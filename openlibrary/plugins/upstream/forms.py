import web
from infogami.infobase.client import ClientException
from infogami.core import forms

from openlibrary.i18n import lgettext as _
from openlibrary.utils.form import Form, Textbox, Password, Hidden, Validator, RegexpValidator
from openlibrary import accounts
from openlibrary.accounts import InternetArchiveAccount
from . import spamcheck

def find_account(username=None, lusername=None, email=None):
    return accounts.find(username=username, lusername=lusername, email=email)

def find_ia_account(email=None):
    ia_account = InternetArchiveAccount.get(email=email)
    return ia_account

Login = Form(
    Textbox('username', description=_('Username'), klass='required'),
    Password('password', description=_('Password'), klass='required'),
    Hidden('redirect')
)
forms.login = Login

email_already_used = Validator(_("No user registered with this email address"), lambda email: find_account(email=email) is not None)
email_not_already_used = Validator(_("Email already registered"), lambda email: not find_ia_account(email=email))
email_not_disposable = Validator(_("Disposable email not permitted"), lambda email: not email.lower().endswith('dispostable.com'))
email_domain_not_blocked = Validator(_("Your email provider is not recognized."), lambda email: not spamcheck.is_spam_email(email))
username_validator = Validator(_("Username already used"), lambda username: not find_account(lusername=username.lower()))

vlogin = RegexpValidator(r"^[A-Za-z0-9-_]{3,20}$", _('Must be between 3 and 20 letters and numbers'))
vpass = RegexpValidator(r".{3,20}", _('Must be between 3 and 20 characters'))
vemail = RegexpValidator(r".*@.*", _("Must be a valid email address"))

class EqualToValidator(Validator):
    def __init__(self, fieldname, message):
        Validator.__init__(self, message, None)
        self.fieldname = fieldname
        self.form = None

    def valid(self, value):
        # self.form will be set by RegisterForm
        return self.form[self.fieldname].value == value

class RegisterForm(Form):
    INPUTS = [
        Textbox('email', description=_('Your email address'),
            klass='required',
            validators=[vemail, email_not_already_used, email_not_disposable, email_domain_not_blocked]),
        Textbox('username', description=_('Choose a screen name'),
            klass='required',
            help=_("Only letters and numbers, please, and at least 3 characters."),
            validators=[vlogin, username_validator]),
        Password('password', description=_('Choose a password'),
            klass='required',
            validators=[vpass]),
        Textbox('password2', description=_('Confirm password'),
            klass='required',
            validators=[vpass, EqualToValidator('password', _("Passwords didn't match."))]),
    ]
    def __init__(self):
        Form.__init__(self, *self.INPUTS)

    def validates(self, source):
        # Set form in each validator so that validators
        # like EqualToValidator can work
        for input in self.inputs:
            for validator in input.validators:
                validator.form = self
        return Form.validates(self, source)

Register = RegisterForm()
forms.register = RegisterForm()

def verify_password(password):
    user = accounts.get_current_user()
    if user is None:
        return False

    try:
        username = user.key.split('/')[-1]
        web.ctx.site.login(username, password)
    except ClientException:
        return False

    return True

validate_password = Validator(_("Invalid password"), verify_password)

ChangePassword = Form(
    Password('password', description=_("Current password"), klass='pwmask required', validators=[validate_password]),
    Password('new_password', description=_("Choose a new password"), klass='pwmask required')
)

ChangeEmail = Form(
    Textbox('email', description=_("Your new email address"), validators=[vemail, email_not_already_used])
)

ForgotPassword = Form(
    Textbox('email', description=_("Your email address"), validators=[vemail, email_already_used])
)

ResetPassword = Form(
    Password('password', description=_("Choose a password"), validators=[vpass])
)
