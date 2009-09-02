import web

from openlibrary.i18n import lgettext as _
from openlibrary.utils.form import Form, Textbox, Password, Validator, RegexpValidator

Login = Form(
    Textbox('username', label=_('Username'), klass='required'),
    Password('password', label=_('Password'), klass='required')
)

email_not_already_used = Validator(_("Email already used"), lambda email: web.ctx.site.find_user_by_email(email) is None)
username_validator = Validator(_("Username already used"), lambda username: web.ctx.site.get('/user/' + username) is None)

vlogin = RegexpValidator(r"^[A-Za-z0-9-_]{3,20}$", 'must be between 3 and 20 letters and numbers') 
vpass = RegexpValidator(r".{3,20}", 'must be between 3 and 20 characters')
vemail = RegexpValidator(r".*@.*", "must be a valid email address")

Register = Form(
    Textbox('email', label=_('Your Email Address'), klass='required', validators=[vemail, email_not_already_used]),
    Textbox('username', label=_('Choose a Username'), klass='required', description=_("Only letters and numbers, please, and at least 3 characters."), 
        validators=[vlogin, username_validator]),
    Password('password', label=_('Choose a Password'), klass='required', validators=[vpass])
)
