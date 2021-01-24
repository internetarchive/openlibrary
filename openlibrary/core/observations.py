"""Module for handling patron observation functionality"""

import requests

from infogami import config
from openlibrary import accounts

# URL for TheBestBookOn
TBBO_URL = config.get('tbbo_url')

def post_observation(data, s3_keys):
    headers = {
        'x-s3-access': s3_keys['access'],
        'x-s3-secret': s3_keys['secret']
    }

    response = requests.post(TBBO_URL + '/api/observations', data=data, headers=headers)

    return response.text
