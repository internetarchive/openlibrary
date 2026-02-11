from dataclasses import dataclass, field
from functools import cached_property

from openlibrary.i18n import gettext as _


@dataclass(frozen=True)
class ScorecardCheck:
    """Represents a metadata quality check for edition scoring."""

    name: str
    score: int
    description: str
    details: str


@dataclass
class EditionScorecard:
    passing_checks: set[ScorecardCheck] = field(default_factory=set)

    @property
    def score(self) -> int:
        """Calculates the total score based on the passing checks."""
        return sum(check.score for check in self.passing_checks)

    @cached_property
    def max_score(self) -> int:
        """Calculates the maximum possible score based on the defined checks."""
        return sum(check.score for check in self.get_checks())

    def get_checks(self) -> list[ScorecardCheck]:
        """Returns a list of ScorecardCheck instances representing the metadata quality checks."""
        checks = []
        for attr_name in dir(self):
            if attr_name in ('score', 'max_score'):
                continue

            attr_value = getattr(self, attr_name)
            if isinstance(attr_value, ScorecardCheck):
                checks.append(attr_value)
        return checks

    has_title = ScorecardCheck(
        name='title',
        score=20,
        description=_('Has title field'),
        details=_(
            'A title field helps patrons identify what the book is, and makes it discoverable via search.'
        ),
    )
    has_cover = ScorecardCheck(
        name='cover',
        score=20,
        description=_('Has cover image'),
        details=_(
            'A cover image helps patrons visually identify the book and makes it more appealing in search results.'
        ),
    )
    has_short_description = ScorecardCheck(
        name='short_description',
        score=10,
        description=_('Has description (50+ characters)'),
        details=_(
            'A brief description helps patrons understand what the book is about.'
        ),
    )
    has_long_description = ScorecardCheck(
        name='long_description',
        score=10,
        description=_('Has description (100+ characters)'),
        details=_('A longer description provides more context about the book content.'),
    )
    has_language = ScorecardCheck(
        name='language',
        score=15,
        description=_('Has language information'),
        details=_(
            'Language information helps patrons filter and find books in their preferred language.'
        ),
    )
    has_author = ScorecardCheck(
        name='author',
        score=10,
        description=_('Has author information'),
        details=_(
            'Author information is crucial for discovery and helps patrons find other works by the same author.'
        ),
    )
    has_publish_year = ScorecardCheck(
        name='publish_year',
        score=5,
        description=_('Has publication year'),
        details=_(
            'Publication year helps patrons understand the context and currency of the content.'
        ),
    )
    has_identifiers = ScorecardCheck(
        name='identifiers',
        score=10,
        description=_('Has identifiers (ISBN, LCCN, IA, or other)'),
        details=_(
            'Identifiers help with cataloging, deduplication, and linking to external resources.'
        ),
    )
    has_lexile = ScorecardCheck(
        name='lexile',
        score=10,
        description=_('Has Lexile measure'),
        details=_(
            'Lexile measures help educators and parents find books at the appropriate reading level.'
        ),
    )
