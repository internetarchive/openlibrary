import web
from infogami.infobase.client import ClientException
from infogami.core import forms

from openlibrary.i18n import lgettext as _
from openlibrary.utils.form import Form, Textbox, Password, Hidden, Validator, RegexpValidator

def find_account(username=None, lusername=None, email=None):
    import account
    return account.Account.find(username=username, lusername=lusername, email=email)

Login = Form(
    Textbox('username', description=_('Username'), klass='required'),
    Password('password', description=_('Password'), klass='required'),
    Hidden('redirect')
)
forms.login = Login

email_already_used = Validator(_("No user registered with this email address"), lambda email: find_account(email=email) is not None)
email_not_already_used = Validator(_("Email already used"), lambda email: find_account(email=email) is None)
email_not_disposable = Validator(_("Disposable email not permitted"), lambda email: not email.lower().endswith('dispostable.com'))
username_validator = Validator(_("Username already used"), lambda username: not find_account(lusername=username.lower()))

vlogin = RegexpValidator(r"^[A-Za-z0-9-_]{3,20}$", _('Must be between 3 and 20 letters and numbers')) 
vpass = RegexpValidator(r".{3,20}", _('Must be between 3 and 20 characters'))
vemail = RegexpValidator(r".*@.*", _("Must be a valid email address"))

Register = Form(
    Textbox("displayname", description=_("Your Full Name")),
    Textbox('email', description=_('Your Email Address'), klass='required', validators=[vemail, email_not_already_used, email_not_disposable]),
    Textbox('username', description=_('Choose a Username'), klass='required', help=_("Only letters and numbers, please, and at least 3 characters."), 
        validators=[vlogin, username_validator]),
    Password('password', description=_('Choose a Password'), klass='required', validators=[vpass])
)

forms.register = Register

def verify_password(password):
    user = web.ctx.site.get_user()
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
    Password('password', description=_("Current Password"), klass='pwmask required', validators=[validate_password]),
    Password('new_password', description=_("Choose a New Password"), klass='pwmask required')
)

ChangeEmail = Form(
    Textbox('email', description=_("Your New Email Address"), validators=[vemail, email_not_already_used])
)

ForgotPassword = Form(
    Textbox('email', description=_("Your Email Address"), validators=[vemail, email_already_used])
)

ResetPassword = Form(
    Password('password', description=_("Choose a Password"), validators=[vpass])
)
