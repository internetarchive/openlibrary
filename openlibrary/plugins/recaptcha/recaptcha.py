"""Recapcha Input to use in web.py forms."""

import web
import urllib
import urllib2
import logging

class Recaptcha(web.form.Input):
    def __init__(self, public_key, private_key):
        self.public_key = public_key
        self._private_key = private_key
        validator = web.form.Validator('Recaptcha failed', self.validate)

        web.form.Input.__init__(self, 'recaptcha', validator)
        self.description = ''
        self.help = ''

        self.error = None

    def validate(self, value=None):
        i = web.input(recaptcha_challenge_field="", recaptcha_response_field="")

        privatekey=self._private_key
        response=i.recaptcha_response_field
        remoteip=web.ctx.ip

        data = "https://www.google.com/recaptcha/api/siteverify?secret=" + privatekey + "&response=" + response + "&remoteip=" + remoteip

        try:
            response = urllib2.urlopen(data, timeout=3).read()
        except urllib2.URLError:
            logging.getLogger("openlibrary").exception('Recaptcha call failed: letting user through')
            return True

        if '\n' in response:
            success, error = response.split('\n', 1)
            if success.lower() != 'true':
                self.error = error.strip()
                return False
            else:
                return True
        else:
            return False

