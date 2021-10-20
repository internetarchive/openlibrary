from typing import Union, List, Optional

from openlibrary.book_providers import AbstractBookProvider
from openlibrary.plugins.upstream.models import Edition


class StandardEbooksProvider(AbstractBookProvider):
    short_name = 'standard_ebooks'
    identifier_key = 'standard_ebooks'
