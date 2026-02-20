import typing
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
class ScorecardSection:
    name: str
    details: str = ''
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
            if attr_name in ('score', 'max_score', 'passing_checks'):
                continue

            attr_value = getattr(self, attr_name)
            if isinstance(attr_value, ScorecardCheck):
                checks.append(attr_value)
        return checks


@dataclass
class Scorecard(ScorecardSection):
    @property
    def passing_checks(self) -> set[ScorecardCheck]:
        """Aggregates passing checks from all sections."""
        return {
            check for section in self.get_sections() for check in section.passing_checks
        }

    @passing_checks.setter
    def passing_checks(self, value):
        pass  # Ignore, we calculate passing checks dynamically from sections

    @typing.override
    def get_checks(self) -> list[ScorecardCheck]:
        # Handle nested sections by recursively gathering checks from any ScorecardSection attributes
        checks = []
        for attr_name in dir(self):
            if attr_name in ('score', 'max_score', 'passing_checks'):
                continue

            attr_value = getattr(self, attr_name)
            if isinstance(attr_value, ScorecardCheck):
                checks.append(attr_value)
            elif isinstance(attr_value, ScorecardSection):
                checks.extend(attr_value.get_checks())
        return checks

    def get_sections(self) -> list[ScorecardSection]:
        """Returns a list of ScorecardSection instances representing the different sections of the scorecard."""
        sections = []
        for attr_name in dir(self):
            if attr_name in ('score', 'max_score', 'passing_checks'):
                continue

            attr_value = getattr(self, attr_name)
            if isinstance(attr_value, ScorecardSection):
                sections.append(attr_value)
        return sections


@dataclass
class EditionDiscoveryScore(ScorecardSection):
    """Scorecard for evaluating the metadata quality of an edition."""

    has_title = ScorecardCheck(
        name='title',
        score=25,
        description=_('Has title field'),
        details=_(
            'A title is essential for discovery and helps patrons identify the book in search results and catalogs.'
        ),
    )
    has_language = ScorecardCheck(
        name='language',
        score=20,
        description=_('Has language information'),
        details=_(
            'Language information helps patrons filter and find books in their preferred language.'
        ),
    )
    # has_author = ScorecardCheck(
    #     name='author',
    #     score=10,
    #     description=_('Has author information'),
    #     details=_(
    #         'Author information is crucial for discovery and helps patrons find other works by the same author.'
    #     ),
    # )

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
    has_ddc = ScorecardCheck(
        name='ddc',
        score=10,
        description=_('Has Dewey Decimal Classification (DDC)'),
        details=_(
            'Dewey Decimal Classification helps with organization, discovery, and recommendations in library catalogs.'
        ),
    )
    has_lcc = ScorecardCheck(
        name='lcc',
        score=10,
        description=_('Has Library of Congress Classification (LCC)'),
        details=_(
            'Library of Congress Classification helps with organization, discovery, and recommendations in library catalogs.'
        ),
    )


@dataclass
class EditionEvaluationScorecard(ScorecardSection):
    has_title = ScorecardCheck(
        name='title',
        score=25,
        description=_('Has title field'),
        details=_(
            'A title is essential for discovery and helps patrons identify the book in search results and catalogs.'
        ),
    )
    has_cover = ScorecardCheck(
        name='cover',
        score=25,
        description=_('Has cover image'),
        details=_(
            'A cover image helps patrons visually identify the book and makes it more appealing in search results.'
        ),
    )
    has_short_description = ScorecardCheck(
        name='short_description',
        score=20,
        description=_('Has a description (50+ characters)'),
        details=_(
            'A brief description helps patrons understand what the book is about.'
        ),
    )
    has_long_description = ScorecardCheck(
        name='long_description',
        score=20,
        description=_('Has a detailed description (100+ characters)'),
        details=_('A longer description provides more context about the book content.'),
    )
    has_language = ScorecardCheck(
        name='language',
        score=10,
        description=_('Has language information'),
        details=_(
            'Language information helps patrons filter and find books in their preferred language.'
        ),
    )
    has_publish_year = ScorecardCheck(
        name='publish_year',
        score=10,
        description=_('Has publication year'),
        details=_(
            'Publication year helps patrons understand the context and currency of the content.'
        ),
    )


@dataclass
class EditionAccessScorecard(ScorecardSection):
    """Scorecard for evaluating the accessibility of an edition."""

    name: str = _('Edition Access')

    is_readable = ScorecardCheck(
        name='readable',
        score=60,
        description=_('Readable online or via download'),
        details=_(
            'Borrowable and readable books can be accessed by readers, researchers, and all patrons alike.'
        ),
    )

    is_fully_public = ScorecardCheck(
        name='fully_public',
        score=10,
        description=_('Fully open access'),
        details=_(
            'Fully public books can be read online or downloaded without any restrictions, providing excellent access for patrons.'
        ),
    )

    allows_search_inside = ScorecardCheck(
        name='search_inside',
        score=40,
        description=_('Allows search inside'),
        details=_(
            'Books that allow search inside enable patrons to quickly find relevant content within the book, improving discoverability and usability.'
        ),
    )


@dataclass
class EditionScorecard(Scorecard):
    name: str = _('Edition Scorecard')

    access = EditionAccessScorecard(name=_('Access'))
    discovery = EditionDiscoveryScore(
        name=_('Discovery'),
        details=_(
            'How well can this edition be accurately surfaced in searches and recommendations?'
        ),
    )
    evaluation = EditionEvaluationScorecard(
        name=_('Evaluation'),
        details=_(
            'How well can a patron determine if this edition is relevant to their needs before accessing it?'
        ),
    )
