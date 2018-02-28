"""Recapcha Input to use in web.py forms."""

import web
import requests
import logging

class Recaptcha(web.form.Input):
    def __init__(self, public_key, private_key):
        self.public_key = public_key
        self._private_key = private_key
        validator = web.form.Validator('Recaptcha failed', self.validate)

        web.form.Input.__init__(self, 'recaptcha', validator)
        self.description = 'Validator for recaptcha v2'
        self.help = ''

        self.error = None

    def validate(self, value=None):
        i = web.input()
        url = "https://www.google.com/recaptcha/api/siteverify"
        params = {
            'secret': self._private_key,
            'response': i.get('g-recaptcha-response'),
            'remoteip': web.ctx.ip
        }

        try:
            r = requests.get(url, params=params, timeout=3)
        except requests.exceptions.RequestException as e:
            logging.getLogger("openlibrary").exception(
                'Recaptcha call failed: letting user through')
            return True
        
        return r.json().get('success', '')
