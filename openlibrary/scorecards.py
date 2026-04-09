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


# ---------------------------------------------------------------------------
# Edition Access Section
# ---------------------------------------------------------------------------
@dataclass
class EditionAccessSection(ScorecardSection):
    """Scorecard for evaluating the accessibility of an edition."""

    read_access = ScorecardCheck(
        name='read_access',
        score=200,
        description=_('Can be accessed in full online (read / borrowed)'),
        details=_(
            'Borrowable and readable books can be accessed by readers, researchers, and all patrons alike.'
        ),
    )
    search_inside_access = ScorecardCheck(
        name='search_inside_access',
        score=50,
        description=_('Can view snippets via search inside'),
        details=_(
            'Books that allow search inside enable patrons to quickly find relevant content within the book.'
        ),
    )
    # executive_summary = ScorecardCheck(
    #     name='executive_summary',
    #     score=50,
    #     description=_('Has an executive summary'),
    #     details=_(
    #         'An executive summary provides a quick overview of the book content for busy readers.'
    #     ),
    # )
    programatic_access = ScorecardCheck(
        name='programatic_access',
        score=25,
        description=_('Open access (can analyze in full)'),
        details=_(
            'Fully public books can be read online or downloaded without any restrictions, providing excellent access for patrons.'
        ),
    )
    purchase_options = ScorecardCheck(
        name='purchase_options',
        score=25,
        description=_('Has purchase options (ISBN available)'),
        details=_(
            'An ISBN enables patrons to purchase the book from retailers such as Amazon, BWB, and Bookshop.'
        ),
    )
    library_options = ScorecardCheck(
        name='library_options',
        score=25,
        description=_('Has library options (ISBN or OCLC)'),
        details=_(
            'ISBN or OCLC numbers enable patrons to find the book through library catalogs.'
        ),
    )
    # sample_access = ScorecardCheck(
    #     name='sample_access',
    #     score=25,
    #     description=_('Has a meaningful preview/sample'),
    #     details=_(
    #         'A sizeable preview (e.g. ~10%%) lets patrons evaluate the book before committing.'
    #     ),
    # )
    fan_fiction = ScorecardCheck(
        name='fan_fiction',
        score=20,
        description=_('Has fan fiction link (Archive of Our Own)'),
        details=_(
            'A link to Archive of Our Own helps readers discover related fan-created works.'
        ),
    )
    wikipedia = ScorecardCheck(
        name='wikipedia',
        score=20,
        description=_('Has Wikipedia link'),
        details=_(
            'A Wikipedia link provides additional context and encyclopedic information about the work.'
        ),
    )
    # micro_synopsis = ScorecardCheck(
    #     name='micro_synopsis',
    #     score=20,
    #     description=_('Has a micro synopsis'),
    #     details=_(
    #         'A very short, spoiler-free synopsis helps patrons quickly assess relevance.'
    #     ),
    # )
    # quotes = ScorecardCheck(
    #     name='quotes',
    #     score=10,
    #     description=_('Has quotes/excerpts'),
    #     details=_(
    #         'Excerpts and quotes let patrons sample the writing style and content.'
    #     ),
    # )
    # index = ScorecardCheck(
    #     name='index',
    #     score=10,
    #     description=_('Has an index (scandata.xml)'),
    #     details=_(
    #         'An index enables quick lookup of specific topics within the book.'
    #     ),
    # )
    # verso_page = ScorecardCheck(
    #     name='verso_page',
    #     score=8,
    #     description=_('Has a verso page (scandata.xml)'),
    #     details=_(
    #         'A verso page (title page verso) is useful for librarians cataloging the book.'
    #     ),
    # )
    # table_of_contents_page = ScorecardCheck(
    #     name='table_of_contents_page',
    #     score=5,
    #     description=_('Has table of contents page (toc.xml)'),
    #     details=_(
    #         'A linked table of contents page helps patrons navigate within the scanned book.'
    #     ),
    # )
    # ngrams = ScorecardCheck(
    #     name='ngrams',
    #     score=5,
    #     description=_('Has Book Genome n-grams extracted'),
    #     details=_(
    #         'N-gram data from the Book Genome Project enables advanced text analysis and discovery.'
    #     ),
    # )
    first_sentence = ScorecardCheck(
        name='first_sentence',
        score=2,
        description=_('Has first sentence'),
        details=_(
            'The first sentence gives patrons an immediate taste of the writing style.'
        ),
    )


# ---------------------------------------------------------------------------
# Edition Discovery Section
# ---------------------------------------------------------------------------
@dataclass
class EditionDiscoverySection(ScorecardSection):
    """Scorecard for evaluating how well an edition can be found via search."""

    title = ScorecardCheck(
        name='title',
        score=50,
        description=_('Has title field'),
        details=_(
            'A title is essential for discovery and helps patrons identify the book in search results and catalogs.'
        ),
    )
    author_name = ScorecardCheck(
        name='author_name',
        score=40,
        description=_('Has author information'),
        details=_(
            'Author information is crucial for discovery and helps patrons find other works by the same author.'
        ),
    )
    genre_tags = ScorecardCheck(
        name='genre_tags',
        score=25,
        description=_('Has genre/category tags'),
        details=_(
            'Genre tags help patrons search by genre or category to discover relevant books.'
        ),
    )
    series = ScorecardCheck(
        name='series',
        score=20,
        description=_('Has series information'),
        details=_(
            'Series information helps patrons search by series and discover related books.'
        ),
    )
    table_of_contents = ScorecardCheck(
        name='table_of_contents',
        score=20,
        description=_('Has table of contents'),
        details=_(
            'Table of contents entries are indexed and searchable, improving discoverability.'
        ),
    )
    classifications = ScorecardCheck(
        name='classifications',
        score=15,
        description=_('Has DDC or LCC classification'),
        details=_(
            'Dewey Decimal or Library of Congress classifications help with organization and shelf browsing.'
        ),
    )
    language = ScorecardCheck(
        name='language',
        score=15,
        description=_('Has language information'),
        details=_(
            'Language information helps patrons filter and find books in their preferred language.'
        ),
    )
    isbn = ScorecardCheck(
        name='isbn',
        score=15,
        description=_('Has ISBN'),
        details=_(
            'ISBNs allow searching by barcode scanner and help with identification.'
        ),
    )
    lexile = ScorecardCheck(
        name='lexile',
        score=5,
        description=_('Has Lexile measure'),
        details=_(
            'Lexile measures help educators and parents find books at the appropriate reading level.'
        ),
    )
    star_ratings = ScorecardCheck(
        name='star_ratings',
        score=5,
        description=_('Has star ratings (ranking signal)'),
        details=_(
            'Star ratings contribute to search ranking so better-rated books surface higher.'
        ),
    )
    on_readinglogs = ScorecardCheck(
        name='on_readinglogs',
        score=3,
        description=_('Appears on reading logs (ranking signal)'),
        details=_(
            'Presence on reading logs is a popularity signal that helps with search ranking.'
        ),
    )
    on_lists = ScorecardCheck(
        name='on_lists',
        score=2,
        description=_('Appears on lists (ranking signal)'),
        details=_(
            'Presence on user lists is a popularity signal that helps with search ranking.'
        ),
    )
    contributor_names = ScorecardCheck(
        name='contributor_names',
        score=1,
        description=_('Has contributor names'),
        details=_(
            'Contributor names (editors, illustrators, translators) enable searching by contributor.'
        ),
    )


# ---------------------------------------------------------------------------
# Edition Evaluation Section
# ---------------------------------------------------------------------------
@dataclass
class EditionEvaluationSection(ScorecardSection):
    """Scorecard for evaluating how well a patron can assess this edition."""

    # preview = ScorecardCheck(
    #     name='preview',
    #     score=50,
    #     description=_('Has a preview (Amazon/Google Books)'),
    #     details=_(
    #         'A preview from Amazon or Google Books lets patrons evaluate the book content.'
    #     ),
    # )
    basic_description = ScorecardCheck(
        name='basic_description',
        score=40,
        description=_('Has a description'),
        details=_(
            'A description helps patrons understand what the book is about before accessing it.'
        ),
    )
    cover = ScorecardCheck(
        name='cover',
        score=35,
        description=_('Has cover image'),
        details=_(
            'A cover image helps patrons visually identify the book and makes it more appealing in search results.'
        ),
    )
    table_of_contents = ScorecardCheck(
        name='table_of_contents',
        score=30,
        description=_('Has table of contents'),
        details=_(
            'A table of contents helps patrons evaluate the structure and scope of the book.'
        ),
    )
    genre_tags = ScorecardCheck(
        name='genre_tags',
        score=25,
        description=_('Has genre/category tags'),
        details=_(
            'Genre tags help patrons quickly assess whether a book matches their interests.'
        ),
    )
    star_ratings = ScorecardCheck(
        name='star_ratings',
        score=20,
        description=_('Has star ratings (popularity signal)'),
        details=_(
            'Star ratings from other readers help patrons gauge the quality and reception of the book.'
        ),
    )
    # awards = ScorecardCheck(
    #     name='awards',
    #     score=15,
    #     description=_('Has awards'),
    #     details=_(
    #         'Award information signals quality and critical acclaim.'
    #     ),
    # )
    rich_description = ScorecardCheck(
        name='rich_description',
        score=10,
        description=_('Has a rich description (50+ characters)'),
        details=_(
            'A detailed description (50+ characters) provides more context to help patrons evaluate relevance.'
        ),
    )
    readinglog_counts = ScorecardCheck(
        name='readinglog_counts',
        score=10,
        description=_('Has reading log activity (popularity signal)'),
        details=_(
            'Reading log activity from other patrons signals the book is being actively read.'
        ),
    )
    list_count = ScorecardCheck(
        name='list_count',
        score=10,
        description=_('Appears on lists (popularity signal)'),
        details=_(
            'Presence on curated lists helps patrons gauge relevance and community interest.'
        ),
    )
    page_count = ScorecardCheck(
        name='page_count',
        score=10,
        description=_('Has page count'),
        details=_(
            'Page count helps patrons estimate the length and time commitment of the book.'
        ),
    )
    series = ScorecardCheck(
        name='series',
        score=10,
        description=_('Has series information'),
        details=_(
            'Series information helps patrons understand the book\'s place in a broader narrative.'
        ),
    )
    # content_warnings = ScorecardCheck(
    #     name='content_warnings',
    #     score=5,
    #     description=_('Has content warnings'),
    #     details=_(
    #         'Content warnings help patrons make informed decisions about sensitive material.'
    #     ),
    # )
    author_photo = ScorecardCheck(
        name='author_photo',
        score=5,
        description=_('Has author photo'),
        details=_(
            'An author photo helps patrons visually recognize the author.'
        ),
    )
    first_publish_year = ScorecardCheck(
        name='first_publish_year',
        score=5,
        description=_('Has first publication year'),
        details=_(
            'The first publication year helps patrons understand when the work originally appeared.'
        ),
    )
    publish_year = ScorecardCheck(
        name='publish_year',
        score=5,
        description=_('Has publication year'),
        details=_(
            'Publication year helps patrons understand the context and currency of the content.'
        ),
    )
    # rich_characters = ScorecardCheck(
    #     name='rich_characters',
    #     score=5,
    #     description=_('Has rich characters on work'),
    #     details=_(
    #         'Character information (distinct from subjects) helps patrons evaluate works of fiction.'
    #     ),
    # )
    author_bio = ScorecardCheck(
        name='author_bio',
        score=3,
        description=_('Has author biography'),
        details=_(
            'An author biography helps patrons understand the author\'s background and expertise.'
        ),
    )
    publisher = ScorecardCheck(
        name='publisher',
        score=2,
        description=_('Has publisher'),
        details=_(
            'Publisher information helps patrons evaluate the credibility and source of the book.'
        ),
    )
    author_links = ScorecardCheck(
        name='author_links',
        score=2,
        description=_('Has author links'),
        details=_(
            'Links to author websites or profiles provide additional context about the author.'
        ),
    )


# ---------------------------------------------------------------------------
# Composite Edition Scorecard
# ---------------------------------------------------------------------------
@dataclass
class EditionScorecard(Scorecard):
    name: str = _('Edition Scorecard')

    access = EditionAccessSection(name=_('Access'))
    discovery = EditionDiscoverySection(
        name=_('Discovery'),
        details=_(
            'How well can this edition be accurately surfaced in searches and recommendations?'
        ),
    )
    evaluation = EditionEvaluationSection(
        name=_('Evaluation'),
        details=_(
            'How well can a patron determine if this edition is relevant to their needs before accessing it?'
        ),
    )
