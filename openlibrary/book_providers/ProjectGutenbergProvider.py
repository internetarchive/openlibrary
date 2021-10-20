from typing import Union, List, Optional

from openlibrary.book_providers import AbstractBookProvider
from openlibrary.plugins.upstream.models import Edition


class ProjectGutenbergProvider(AbstractBookProvider):
    short_name = 'gutenberg'
    identifier_key = 'project_gutenberg'
