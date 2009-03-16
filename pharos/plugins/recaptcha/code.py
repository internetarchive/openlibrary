
from infogami.core.forms import register
from infogami import config

import recaptcha

register.inputs = list(register.inputs)
register.inputs.append(recaptcha.Recapcha(config.recaptcha_public_key, config.recaptcha_private_key))
