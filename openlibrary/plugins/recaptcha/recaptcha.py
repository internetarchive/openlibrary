"""Recapcha Input to use in web.py forms."""

import web
import urllib

_recaptcha_html = """
<script type="text/javascript"
   src="http://api.recaptcha.net/challenge?k=KEY">
</script>

<noscript>
   <iframe src="http://api.recaptcha.net/noscript?k=KEY"
       height="300" width="500" frameborder="0"></iframe><br>
   <textarea name="recaptcha_challenge_field" rows="3" cols="40">
   </textarea>
   <input type="hidden" name="recaptcha_response_field" 
       value="manual_challenge">
</noscript>
"""

class Recapcha(web.form.Input):
    def __init__(self, public_key, private_key):
        self.public_key = public_key
        self._private_key = private_key
        validator = web.form.Validator('Recaptcha failed', self.validate)

        web.form.Input.__init__(self, 'recaptcha', validator)
        self.description = ''
        self.help = ''

        self.error = None

    def render(self):
        if self.error:
            key = self.public_key + '&error=' + self.error
        else:
            key = self.public_key
        return _recaptcha_html.replace('KEY', key)

    def validate(self, value):
        i = web.input(recaptcha_challenge_field="", recaptcha_response_field="")

        data = dict(
            privatekey=self._private_key,
            challenge=i.recaptcha_challenge_field,
            response=i.recaptcha_response_field,
            remoteip=web.ctx.ip)

        response = urllib.urlopen('http://api-verify.recaptcha.net/verify', urllib.urlencode(data)).read()
        if '\n' in response:
            success, error = response.split('\n', 1)
            if success.lower() != 'true':
                self.error = error.strip()
                return False
            else:
                return True
        else:
            return False

