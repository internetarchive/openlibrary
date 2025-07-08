"""Recapcha Input to use in web.py forms."""

import logging

import requests
import web

logger = logging.getLogger("openlibrary")

INVALIDATING_ERRORS = [
    "invalid-input-secret",
    "missing-input-secret",
    "missing-input-response",
    "invalid-input-response",
    "bad-request",
    "timeout-or-duplicate",
]


class Recaptcha(web.form.Input):
    def __init__(self, public_key, private_key) -> None:
        self.public_key = public_key
        self._private_key = private_key
        validator = web.form.Validator('Recaptcha failed', self.validate)

        web.form.Input.__init__(self, 'recaptcha', validator)
        self.description = 'Validator for recaptcha v2'
        self.help = ''

        self.error = None

    def validate(self, value=None):
        def accept_error(error_codes: list[str]) -> bool:
            return not any(error in INVALIDATING_ERRORS for error in error_codes)

        i = web.input()
        url = "https://www.google.com/recaptcha/api/siteverify"
        params = {
            'secret': self._private_key,
            'response': i.get('g-recaptcha-response'),
            'remoteip': web.ctx.ip,
        }

        try:
            r = requests.get(url, params=params, timeout=3)
        except requests.exceptions.RequestException:
            logger.exception('Recaptcha call failed: letting user through')
            return True

        data = r.json()
        if not data.get('success', False) and 'error-codes' in data:
            logger.error(f"Recaptcha Error: {data['error-codes']}")
            return accept_error(data['error-codes'])

        return data.get('success', '')
