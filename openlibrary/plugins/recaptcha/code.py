
# from infogami.core.forms import register
# from infogami import config
#
# import recaptcha
#
# if config.get('plugin_recaptcha') is not None:
#     public_key = config.plugin_recaptcha.public_key
#     private_key = config.plugin_recaptcha.private_key
# else:
#     public_key = config.recaptcha_public_key
#     private_key = config.recaptcha_private_key
#
# register.inputs = list(register.inputs)
# register.inputs.append(recaptcha.Recaptcha(public_key, private_key))
