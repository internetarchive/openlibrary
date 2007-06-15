from web.form import *
import db
from infogami.utils import i18n
from infogami.utils.context import context

_ = i18n.i18n()

login = Form(
    Textbox('username', description=_.USERNAME),
    Password('password', description=_.PASSWORD),
    Checkbox('remember', description=_.REMEMBER_ME)
)

register = Form(
    Textbox('username', 
            Validator(
                _.USERNAME_ALREADY_EXISTS,
                lambda name: not db.get_user_by_name(name)),
            description=_.USERNAME),
    Textbox('email', notnull, description=_.EMAIL),
    Password('password', notnull, description=_.PASSWORD),
    Password('password2', notnull, description=_.CONFIRM_PASSWORD),
    validators = [
        Validator(_.PASSWORDS_DID_NOT_MATCH, lambda i: i.password == i.password2)]    
)

login_preferences = Form(
    Password("oldpassword", notnull, description=_.CURRENT_PASSWORD),
    Password("password", notnull, description=_.NEW_PASSWORD),
    Password("password2", notnull, description=_.CONFIRM_PASSWORD),
    Button("Save"),
    validators = [
        Validator(_.INCORRECT_PASSWORD, lambda i: i.oldpassword == context.user.password),
        Validator(_.PASSWORDS_DID_NOT_MATCH, lambda i: i.password == i.password2)]
)
