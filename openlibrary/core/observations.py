"""Module for handling patron observation functionality"""

from collections import defaultdict, namedtuple

from infogami import config
from infogami.utils.view import public
from openlibrary import accounts
from openlibrary.utils import extract_numeric_id_from_olid
from openlibrary.utils.dateutil import DATE_ONE_MONTH_AGO, DATE_ONE_WEEK_AGO

from . import cache
from . import db

ObservationIds = namedtuple('ObservationIds', ['type_id', 'value_id'])
ObservationKeyValue = namedtuple('ObservationKeyValue', ['key', 'value'])

OBSERVATIONS = {
    'observations': [
        {
            'id': 1,
            'label': _('Pace'),
            'description': _('How would you rate the pacing of this book?'),
            'multi_choice': True,
            'order': [4, 5, 6, 7],
            'values': [
                {'id': 1, 'name': _('Slow'), 'deleted': True},
                {'id': 2, 'name': _('Medium'), 'deleted': True},
                {'id': 3, 'name': _('Fast'), 'deleted': True},
                {'id': 4, 'name': _('Slow paced')},
                {'id': 5, 'name': _('Medium paced')},
                {'id': 6, 'name': _('Fast paced')},
                {'id': 7, 'name': _('Meandering')},
            ]
        },
        {
            'id': 2,
            'label': _('Enjoyability'),
            'description': _('How much did you enjoy reading this book?'),
            'multi_choice': True,
            'order': [3, 7, 8, 9],
            'values': [
                {'id': 1, 'name': _('Not applicable'), 'deleted': True},
                {'id': 2, 'name': _('Very boring'), 'deleted': True},
                {'id': 4, 'name': _('Neither entertaining nor boring'), 'deleted': True},
                {'id': 5, 'name': _('Entertaining'), 'deleted': True},
                {'id': 6, 'name': _('Very entertaining'), 'deleted': True},
                {'id': 3, 'name': _('Boring')},
                {'id': 7, 'name': _('Engaging')},
                {'id': 8, 'name': _('Exciting')},
                {'id': 9, 'name': _('Neutral')},
            ],
        },
        {
            'id': 3,
            'label': _('Clarity'),
            'description': _('How clearly was this book written and presented?'),
            'multi_choice': True,
            'order': [6, 7, 8, 9, 10, 11, 12, 13],
            'values': [
                {'id': 1, 'name': _('Not applicable'), 'deleted': True},
                {'id': 2, 'name': _('Very unclearly'), 'deleted': True},
                {'id': 3, 'name': _('Unclearly'), 'deleted': True},
                {'id': 4, 'name': _('Clearly'), 'deleted': True},
                {'id': 5, 'name': _('Very clearly'), 'deleted': True},
                {'id': 6, 'name': _('Succinct')},
                {'id': 7, 'name': _('Dense')},
                {'id': 8, 'name': _('Incomprehensible')},
                {'id': 9, 'name': _('Confusing')},
                {'id': 10, 'name': _('Clearly written')},
                {'id': 11, 'name': _('Effective explanations')},
                {'id': 12, 'name': _('Well organized')},
                {'id': 13, 'name': _('Disorganized')},
            ],
        },
        {
            'id': 4,
            'label': _('Jargon'),
            'description': _('How technical is the content?'),
            'multi_choice': False,
            'order': [1, 2, 3, 4, 5],
            'values': [
                {'id': 1, 'name': _('Not applicable')},
                {'id': 2, 'name': _('Not technical')},
                {'id': 3, 'name': _('Somewhat technical')},
                {'id': 4, 'name': _('Technical')},
                {'id': 5, 'name': _('Very technical')}
            ],
            'deleted': True
        },
        {
            'id': 5,
            'label': _('Originality'),
            'description': _('How original is this book?'),
            'multi_choice': False,
            'order': [1, 2, 3, 4, 5],
            'values': [
                {'id': 1, 'name': _('Not applicable')},
                {'id': 2, 'name': _('Very unoriginal')},
                {'id': 3, 'name': _('Somewhat unoriginal')},
                {'id': 4, 'name': _('Somewhat original')},
                {'id': 5, 'name': _('Very original')}
            ],
            'deleted': True
        },
        {
            'id': 6,
            'label': _('Difficulty'),
            'description': _('How would you rate the difficulty of ')
                           _('this book for a general audience?'),
            'multi_choice': True,
            'order': [6, 7, 8, 9, 10, 11, 12],
            'values': [
                {'id': 1, 'name': _('Not applicable'), 'deleted': True},
                {'id': 2, 'name': _('Requires domain expertise'), 'deleted': True},
                {'id': 3, 'name': _('A lot of prior knowledge needed'), 'deleted': True},
                {'id': 4, 'name': _('Some prior knowledge needed'), 'deleted': True},
                {'id': 5, 'name': _('No prior knowledge needed'), 'deleted': True},
                {'id': 6, 'name': _('Beginner')},
                {'id': 7, 'name': _('Intermediate')},
                {'id': 8, 'name': _('Advanced')},
                {'id': 9, 'name': _('Expert')},
                {'id': 10, 'name': _('University')},
                {'id': 11, 'name': _('Layman')},
                {'id': 12, 'name': _('Juvenile')},
            ],
        },
        {
            'id': 7,
            'label': _('Usefulness'),
            'description': _('How useful is the content of this book?'),
            'multi_choice': False,
            'order': [1, 2, 3, 4, 5],
            'values': [
                {'id': 1, 'name': _('Not applicable')},
                {'id': 2, 'name': _('Not useful')},
                {'id': 3, 'name': _('Somewhat useful')},
                {'id': 4, 'name': _('Useful')},
                {'id': 5, 'name': _('Very useful')}
            ],
            'deleted': True
        },
        {
            'id': 8,
            'label': _('Breadth'),
            'description': _("How would you describe the breadth and depth of this book?"),
            'multi_choice': True,
            'order': [7, 8, 9, 10, 11, 12, 13],
            'values': [
                {'id': 1, 'name': _('Not applicable'), 'deleted': True},
                {'id': 2, 'name': _('Much more deep'), 'deleted': True},
                {'id': 3, 'name': _('Somewhat more deep'), 'deleted': True},
                {'id': 4, 'name': _('Equally broad and deep'), 'deleted': True},
                {'id': 5, 'name': _('Somewhat more broad'), 'deleted': True},
                {'id': 6, 'name': _('Much more broad'), 'deleted': True},
                {'id': 7, 'name': _('Comprehensive')},
                {'id': 8, 'name': _('Not comprehensive')},
                {'id': 9, 'name': _('Focused')},
                {'id': 10, 'name': _('Interdisciplinary')},
                {'id': 11, 'name': _('Extraneous')},
                {'id': 12, 'name': _('Shallow')},
                {'id': 13, 'name': _('Introductory')},
            ],
        },
        {
            'id': 9,
            'label': _('Objectivity'),
            'description': _('Are there causes to question the accuracy of this book?'),
            'multi_choice': True,
            'order': [1, 2, 3, 4, 5, 6, 7, 8],
            'values': [
                {'id': 1, 'name': _('Not applicable')},
                {'id': 2, 'name': _('No, it seems accurate')},
                {'id': 3, 'name': _('Yes, it needs citations')},
                {'id': 4, 'name': _('Yes, it is inflammatory')},
                {'id': 5, 'name': _('Yes, it has typos')},
                {'id': 6, 'name': _('Yes, it is inaccurate')},
                {'id': 7, 'name': _('Yes, it is misleading')},
                {'id': 8, 'name': _('Yes, it is biased')}
            ],
            'deleted': True
        },
        {
            'id': 10,
            'label': _('Genres'),
            'description': _('What are the genres of this book?'),
            'multi_choice': True,
            'order': [1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17,
                      18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31,
                      32, 33],
            'values': [
                {'id': 1, 'name': _('Sci-fi')},
                {'id': 2, 'name': _('Philosophy'), 'deleted': True},
                {'id': 3, 'name': _('Satire')},
                {'id': 4, 'name': _('Poetry')},
                {'id': 5, 'name': _('Memoir')},
                {'id': 6, 'name': _('Paranormal')},
                {'id': 7, 'name': _('Mystery')},
                {'id': 8, 'name': _('Humor')},
                {'id': 9, 'name': _('Horror')},
                {'id': 10, 'name': _('Fantasy')},
                {'id': 11, 'name': _('Drama')},
                {'id': 12, 'name': _('Crime')},
                {'id': 13, 'name': _('Graphical')},
                {'id': 14, 'name': _('Classic')},
                {'id': 15, 'name': _('Anthology')},
                {'id': 16, 'name': _('Action')},
                {'id': 17, 'name': _('Romance')},
                {'id': 18, 'name': _('How-to')},
                {'id': 19, 'name': _('Encyclopedia')},
                {'id': 20, 'name': _('Dictionary')},
                {'id': 21, 'name': _('Technical')},
                {'id': 22, 'name': _('Reference')},
                {'id': 23, 'name': _('Textbook')},
                {'id': 24, 'name': _('Biographical')},
                {'id': 25, 'name': _('Fiction')},
                {'id': 26, 'name': _('Nonfiction')},
                {'id': 27, 'name': _('Biography')},
                {'id': 28, 'name': _('Based on a true story')},
                {'id': 29, 'name': _('Exploratory')},
                {'id': 30, 'name': _('Research')},
                {'id': 31, 'name': _('Philosophical')},
                {'id': 32, 'name': _('Essay')},
                {'id': 33, 'name': _('Review')},
            ]
        },
        {
            'id': 11,
            'label': _('Fictionality'),
            'description': _("Is this book a work of fact or fiction?"),
            'multi_choice': False,
            'order': [1, 2, 3],
            'values': [
                {'id': 1, 'name': _('Nonfiction')},
                {'id': 2, 'name': _('Fiction')},
                {'id': 3, 'name': _('Biography')}
            ],
            'deleted': True
        },
        {
            'id': 12,
            'label': _('Audience'),
            'description': _("What are the intended age groups for this book?"),
            'multi_choice': True,
            'order': [1, 2, 3, 4, 5, 6, 7],
            'values': [
                {'id': 1, 'name': _('Experts')},
                {'id': 2, 'name': _('College')},
                {'id': 3, 'name': _('High school')},
                {'id': 4, 'name': _('Elementary')},
                {'id': 5, 'name': _('Kindergarten')},
                {'id': 6, 'name': _('Baby')},
                {'id': 7, 'name': _('General audiences')}
            ],
            'deleted': True
        },
        {
            'id': 13,
            'label': _('Mood'),
            'description': _('What are the moods of this book?'),
            'multi_choice': True,
            'order': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26],
            'values': [
                {'id': 1, 'name': _('Scientific')},
                {'id': 2, 'name': _('Dry')},
                {'id': 3, 'name': _('Emotional')},
                {'id': 4, 'name': _('Strange')},
                {'id': 5, 'name': _('Suspenseful')},
                {'id': 6, 'name': _('Sad')},
                {'id': 7, 'name': _('Dark')},
                {'id': 8, 'name': _('Lonely')},
                {'id': 9, 'name': _('Tense')},
                {'id': 10, 'name': _('Fearful')},
                {'id': 11, 'name': _('Angry')},
                {'id': 12, 'name': _('Hopeful')},
                {'id': 13, 'name': _('Lighthearted')},
                {'id': 14, 'name': _('Calm')},
                {'id': 15, 'name': _('Informative')},
                {'id': 16, 'name': _('Ominous')},
                {'id': 17, 'name': _('Mysterious')},
                {'id': 18, 'name': _('Romantic')},
                {'id': 19, 'name': _('Whimsical')},
                {'id': 20, 'name': _('Idyllic')},
                {'id': 21, 'name': _('Melancholy')},
                {'id': 22, 'name': _('Humorous')},
                {'id': 23, 'name': _('Gloomy')},
                {'id': 24, 'name': _('Reflective')},
                {'id': 25, 'name': _('Inspiring')},
                {'id': 26, 'name': _('Cheerful')},
            ]
        },
        {
            'id': 14,
            'label': _('Impressions'),
            'description': _('How did you feel about this book and do you recommend it?'),
            'multi_choice': True,
            'order': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14],
            'values': [
                {'id': 1, 'name': _('Recommend')},
                {'id': 2, 'name': _('Highly recommend')},
                {'id': 3, 'name': _("Don't recommend")},
                {'id': 4, 'name': _('Field defining')},
                {'id': 5, 'name': _('Actionable')},
                {'id': 6, 'name': _('Forgettable')},
                {'id': 7, 'name': _('Quotable')},
                {'id': 8, 'name': _('Citable')},
                {'id': 9, 'name': _('Original')},
                {'id': 10, 'name': _('Unremarkable')},
                {'id': 11, 'name': _('Life changing')},
                {'id': 12, 'name': _('Best in class')},
                {'id': 13, 'name': _('Overhyped')},
                {'id': 14, 'name': _('Underrated')},
            ]
        },
        {
            'id': 15,
            'label': _('Type'),
            'description': _('How would you classify this work?'),
            'multi_choice': True,
            'order': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
            'values': [
                {'id': 1, 'name': _('Fiction')},
                {'id': 2, 'name': _('Nonfiction')},
                {'id': 3, 'name': _('Biography')},
                {'id': 4, 'name': _('Based on a true story')},
                {'id': 5, 'name': _('Textbook')},
                {'id': 6, 'name': _('Reference')},
                {'id': 7, 'name': _('Exploratory')},
                {'id': 8, 'name': _('Research')},
                {'id': 9, 'name': _('Philosophical')},
                {'id': 10, 'name': _('Essay')},
                {'id': 11, 'name': _('Review')},
                {'id': 12, 'name': _('Classic')},
            ],
            'deleted': True
        },
        {
            'id': 16,
            'label': _('Length'),
            'description': _('How would you rate or describe the length of this book?'),
            'multi_choice': True,
            'order': [1, 2, 3],
            'values': [
                {'id': 1, 'name': _('Short')},
                {'id': 2, 'name': _('Medium')},
                {'id': 3, 'name': _('Long')},
            ]
        },
        {
            'id': 17,
            'label': _('Credibility'),
            'description': _('How factually accurate and reliable ')
                           _('is the content of this book?'),
            'multi_choice': True,
            'order': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
            'values': [
                {'id': 1, 'name': _('Accurate')},
                {'id': 2, 'name': _('Inaccurate')},
                {'id': 3, 'name': _('Outdated')},
                {'id': 4, 'name': _('Evergreen')},
                {'id': 5, 'name': _('Biased')},
                {'id': 6, 'name': _('Objective')},
                {'id': 7, 'name': _('Subjective')},
                {'id': 8, 'name': _('Rigorous')},
                {'id': 9, 'name': _('Misleading')},
                {'id': 10, 'name': _('Controversial')},
                {'id': 11, 'name': _('Trendy')},
            ]
        },
        {
            'id': 18,
            'label': _('Features'),
            'description': _('What text features does this book utilize?')
                           _('does this book make use of?'),
            'multi_choice': True,
            'order': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
            'values': [
                {'id': 1, 'name': _('Tables, diagrams, and figures')},
                {'id': 2, 'name': _('Problem sets')},
                {'id': 3, 'name': _('Proofs')},
                {'id': 4, 'name': _('Interviews')},
                {'id': 5, 'name': _('Table of contents')},
                {'id': 6, 'name': _('Illustrations')},
                {'id': 7, 'name': _('Index')},
                {'id': 8, 'name': _('Glossary')},
                {'id': 9, 'name': _('Chapters')},
                {'id': 10, 'name': _('Appendix')},
                {'id': 11, 'name': _('Bibliography')},
            ]
        },
        {
            'id': 19,
            'label': _('Content Warnings'),
            'description': _('Does this book contain objectionable content?'),
            'multi_choice': True,
            'order': [1, 2, 3, 4, 5, 6],
            'values': [
                {'id': 1, 'name': _('Adult themes')},
                {'id': 2, 'name': _('Trigger warnings')},
                {'id': 3, 'name': _('Offensive language')},
                {'id': 4, 'name': _('Graphic imagery')},
                {'id': 5, 'name': _('Insensitivity')},
                {'id': 6, 'name': _('Racism')},
                {'id': 7, 'name': _('Sexual themes')},
                {'id': 8, 'name': _('Drugs')},
            ]
        },
        {
            'id': 20,
            'label': _('Style'),
            'description': _('What type of verbiage, nomenclature, ')
                           _('or symbols are employed in this book?'),
            'multi_choice': True,
            'order': [1, 2, 3, 4, 5],
            'values': [
                {'id': 1, 'name': _('Technical')},
                {'id': 2, 'name': _('Jargony')},
                {'id': 3, 'name': _('Neologisms')},
                {'id': 4, 'name': _('Slang')},
                {'id': 5, 'name': _('Olde')},
            ]
        },
        {
            'id': 21,
            'label': _('Purpose'),
            'description': _('Why should someone read this book?'),
            'multi_choice': True,
            'order': [1, 2, 3, 4, 5, 6, 7, 8, 9],
            'values': [
                {'id': 1, 'name': _('Entertainment')},
                {'id': 2, 'name': _('Broaden perspective')},
                {'id': 3, 'name': _('How-to')},
                {'id': 4, 'name': _('Learn about')},
                {'id': 5, 'name': _('Self-help')},
                {'id': 6, 'name': _('Hope')},
                {'id': 7, 'name': _('Inspiration')},
                {'id': 8, 'name': _('Fact checking')},
                {'id': 9, 'name': _('Problem solving')},
            ]
        },
    ]
}

cache_duration = config.get('observation_cache_duration') or 86400


@public
@cache.memoize(engine="memcache", key="observations", expires=cache_duration)
def get_observations():
    """
    Returns a dictionary of observations that are used to populate forms for patron feedback about a book.

    Dictionary has the following structure:
    {
        'observations': [
            {
                'id': 1,
                'label': 'pace',
                'description': 'What is the pace of this book?',
                'multi_choice': False,
                'values': [
                    'slow',
                    'medium',
                    'fast'
                ]
            }
        ]
    }

    If an observation is marked as deleted, it will not be included in the dictionary.

    return: Dictionary of all possible observations that can be made about a book.
    """
    observations_list = []

    for o in OBSERVATIONS['observations']:
        if 'deleted' not in o:
            list_item = {
                'id': o['id'],
                'label': o['label'],
                'description': o['description'],
                'multi_choice': o['multi_choice'],
                'values': _sort_values(o['order'], o['values'])
            }

            observations_list.append(list_item)

    return {'observations': observations_list}

def _sort_values(order_list, values_list):
    """
    Given a list of ordered value IDs and a list of value dictionaries, returns an ordered list of
    values.

    return: An ordered list of values.
    """
    ordered_values = []

    for id in order_list:
        value = next(
            (v['name'] for v in values_list
                if v['id'] == id and not v.get('deleted', False)),
            None
        )
        if value:
            ordered_values.append(value)

    return ordered_values

def _get_deleted_types_and_values():
    """
    Returns a dictionary containing all deleted observation types and values.

    return: Deleted types and values dictionary.
    """
    results = {
        'types': [],
        'values': defaultdict(list)
    }

    for o in OBSERVATIONS['observations']:
        if 'deleted' in o and o['deleted']:
            results['types'].append(o['id'])
        else:
            for v in o['values']:
                if 'deleted' in v and v['deleted']:
                    results['values'][o['id']].append(v['id'])

    return results


def convert_observation_ids(id_dict):
    """
    Given a dictionary of type and value IDs, returns a dictionary of equivalent
    type and value strings.
    return: Dictionary of type and value strings
    """
    types_and_values = _get_all_types_and_values()
    conversion_results = {}

    for k in id_dict:
        if not types_and_values[str(k)].get('deleted', False):
            conversion_results[types_and_values[str(k)]['type']] = [
                types_and_values[str(k)]['values'][str(i)]['name'] for i in id_dict[k]
                if not types_and_values[str(k)]['values'][str(i)].get('deleted', False)
            ]

    # Remove types with no values (all values of type were marked 'deleted'):
    return {k: v for (k, v) in conversion_results.items() if len(v)}


@cache.memoize(
    engine="memcache",
    key="all_observation_types_and_values",
    expires=cache_duration)
def _get_all_types_and_values():
    """
    Returns a dictionary of observation types and values mappings.  The keys for the
    dictionary are the id numbers.
    return: A dictionary of observation id to string value mappings.
    """
    types_and_values = {}

    for o in OBSERVATIONS['observations']:
        types_and_values[str(o['id'])] = {
            'type': o['label'],
            'deleted': o.get('deleted', False),
            'values': {
                str(v['id']): {'name': v['name'], 'deleted': v.get('deleted', False)}
                for v in o['values']
            }
        }

    return types_and_values


@public
def get_observation_metrics(work_olid):
    """
    Returns a dictionary of observation statistics for the given work.  Statistics
    will be used to populate a book's "Reader Observations" component.

    Dictionary will have the following structure:
    {
        'work_id': 12345,
        'total_respondents': 100,
        'observations': [
            {
                'label': 'pace',
                'description': 'What is the pace of this book?',
                'multi_choice': False,
                'total_respondents_for_type': 10,
                'total_responses': 10,
                'values': [
                    {
                        'value': 'fast',
                        'count': 6
                    },
                    {
                        'value': 'medium',
                        'count': 4
                    }
                ]
            }
            ... Other observations omitted for brevity ...
        ]
    }

    If no observations were made for a specific type, that type will be excluded from
    the 'observations' list.  Items in the 'observations.values' list will be
    ordered from greatest count to least.

    return: A dictionary of observation statistics for a work.
    """
    work_id = extract_numeric_id_from_olid(work_olid)
    total_respondents = Observations.total_unique_respondents(work_id)

    metrics = {}
    metrics['work_id'] = work_id
    metrics['total_respondents'] = total_respondents
    metrics['observations'] = []

    if total_respondents > 0:
        respondents_per_type_dict = Observations.count_unique_respondents_by_type(work_id)
        observation_totals = Observations.count_observations(work_id)

        if not observation_totals:
            # It is possible to have a non-zero number of respondents and no
            # observation totals if deleted book tags are present in the
            # observations table.

            return metrics

        current_type_id = observation_totals[0]['type_id']
        observation_item = next(
            (o for o in OBSERVATIONS['observations']
                if current_type_id == o['id'])
        )

        current_observation = {
            'label': observation_item['label'],
            'description': observation_item['description'],
            'multi_choice': observation_item['multi_choice'],
            'total_respondents_for_type':
                respondents_per_type_dict[current_type_id],
            'values': []
        }

        total_responses = 0

        for i in observation_totals:
            if i['type_id'] != current_type_id:
                current_observation['total_responses'] = total_responses
                total_responses = 0
                metrics['observations'].append(current_observation)
                current_type_id = i['type_id']
                observation_item = next(
                    (o for o in OBSERVATIONS['observations']
                        if current_type_id == o['id'])
                )
                current_observation = {
                    'label': observation_item['label'],
                    'description': observation_item['description'],
                    'multi_choice': observation_item['multi_choice'],
                    'total_respondents_for_type':
                        respondents_per_type_dict[current_type_id],
                    'values': []
                }
            current_observation['values'].append({
                'value': next((
                    v['name'] for v in observation_item['values']
                    if v['id'] == i['value_id']
                )),
                'count': i['total']
            })
            total_responses += i['total']

        current_observation['total_responses'] = total_responses
        metrics['observations'].append(current_observation)
    return metrics


class Observations(object):

    NULL_EDITION_VALUE = -1

    @classmethod
    def summary(cls):
        return {
            'total_reviews': {
                'total': Observations.total_reviews(),
                'month': Observations.total_reviews(
                    since=DATE_ONE_MONTH_AGO
                ),
                'week': Observations.total_reviews(
                    since=DATE_ONE_WEEK_AGO
                ),
            },
            'total_books_reviewed': {
                'total': Observations.total_books_reviewed(),
                'month': Observations.total_books_reviewed(
                    since=DATE_ONE_MONTH_AGO
                ),
                'week': Observations.total_books_reviewed(
                    since=DATE_ONE_WEEK_AGO
                ),
            },
            'total_reviewers': {
                'total': Observations.total_unique_respondents(),
                'month': Observations.total_unique_respondents(
                    since=DATE_ONE_MONTH_AGO
                ),
                'week': Observations.total_unique_respondents(
                    since=DATE_ONE_WEEK_AGO
                ),
            }
        }

    @classmethod
    def total_reviews(cls, since=None):
        oldb = db.get_db()
        query = "SELECT COUNT(*) from observations"
        if since:
            query += " WHERE created >= $since"
        return oldb.query(query, vars={'since': since})[0]['count']

    @classmethod
    def total_books_reviewed(cls, since=None):
        oldb = db.get_db()
        query = "SELECT COUNT(DISTINCT(work_id)) from observations"
        if since:
            query += " WHERE created >= $since"
        return oldb.query(query, vars={'since': since})[0]['count']

    @classmethod
    def total_unique_respondents(cls, work_id=None, since=None):
        """
        Returns total number of patrons who have submitted observations for the given work ID.
        If no work ID is passed, returns total number of patrons who have submitted observations
        for any work.

        return: Total number of patrons who have made an observation.
        """
        oldb = db.get_db()
        data = {
            'work_id': work_id,
            'since': since,
        }
        query = "SELECT COUNT(DISTINCT(username)) FROM observations"

        if work_id:
            query += " WHERE work_id = $work_id"
            if since:
                query += " AND created >= $since"
        elif since:
            query += " WHERE created >= $since"
        return oldb.query(query, vars=data)[0]['count']

    @classmethod
    def count_unique_respondents_by_type(cls, work_id):
        """
        Returns the total number of respondents who have made an observation per each type of a work
        ID.

        return: Dictionary of total patron respondents per type id for the given work ID.
        """
        oldb = db.get_db()
        data = {
            'work_id': work_id,
        }
        query = """
            SELECT
              observation_type AS type,
              count(distinct(username)) AS total_respondents
            FROM observations
            WHERE work_id = $work_id """
        deleted_observations = _get_deleted_types_and_values()

        if len(deleted_observations['types']):
            deleted_type_ids = ', '.join(str(i) for i in deleted_observations['types'])
            query += f'AND observation_type not in ({deleted_type_ids}) '

        if len(deleted_observations['values']):
            for key in deleted_observations['values']:
                deleted_value_ids = ', '.join(str(i) for i in deleted_observations['values'][key])
                query += f'AND NOT (observation_type = {str(key)} AND observation_value IN ({deleted_value_ids})) '

        query += 'GROUP BY type'

        return {
            i['type']: i['total_respondents']
            for i in list(oldb.query(query, vars=data))
        }

    @classmethod
    def count_observations(cls, work_id):
        """
        For a given work, fetches the count of each observation made for the work.  Counts are returned in
        a list, grouped by observation type and ordered from highest count to lowest.

        return: A list of value counts for the given work.
        """
        oldb = db.get_db()
        data = {
            'work_id': work_id
        }
        query = """
            SELECT
              observation_type as type_id,
              observation_value as value_id,
              COUNT(observation_value) AS total
            FROM observations
            WHERE observations.work_id = $work_id """

        deleted_observations = _get_deleted_types_and_values()

        if len(deleted_observations['types']):
            deleted_type_ids = ', '.join(str(i) for i in deleted_observations['types'])
            query += f'AND observation_type not in ({deleted_type_ids}) '

        if len(deleted_observations['values']):
            for key in deleted_observations['values']:
                deleted_value_ids = ', '.join(str(i) for i in deleted_observations['values'][key])
                query += f'AND NOT (observation_type = {str(key)} AND observation_value IN ({deleted_value_ids})) '

        query += """
            GROUP BY type_id, value_id
            ORDER BY type_id, total DESC"""

        return list(oldb.query(query, vars=data))

    @classmethod
    def count_distinct_observations(cls, username):
        """
        Fetches the number of works in which the given user has made at least
        one observation.

        return: The number of works for which the given user has made at least
        one observation
        """
        oldb = db.get_db()
        data = {
            'username': username
        }
        query = """
            SELECT
              COUNT(DISTINCT(work_id))
            FROM observations
            WHERE observations.username = $username
        """

        return oldb.query(query, vars=data)[0]['count']

    @classmethod
    def get_key_value_pair(cls, type_id, value_id):
        """
        Given a type ID and value ID, returns a key-value pair of the observation's type and value.

        return: Type and value key-value pair
        """
        observation = next((o for o in OBSERVATIONS['observations'] if o['id'] == type_id))
        key = observation['label']
        value = next((v['name'] for v in observation['values'] if v['id'] == value_id))

        return ObservationKeyValue(key, value)

    @classmethod
    def get_patron_observations(cls, username, work_id=None):
        """
        Returns a list of observation records containing only type and value IDs.

        Gets all of a patron's observation records by default.  Returns only the observations for
        the given work if work_id is passed.

        return: A list of a patron's observations
        """
        oldb = db.get_db()
        data = {
            'username': username,
            'work_id': work_id
        }
        query = """
            SELECT
                observations.observation_type AS type,
                observations.observation_value AS value
            FROM observations
            WHERE observations.username=$username"""
        if work_id:
            query += " AND work_id=$work_id"

        return list(oldb.query(query, vars=data))

    @classmethod
    def get_observations_grouped_by_work(cls, username, limit=25, page=1):
        """
        Returns a list of records which contain a work id and a JSON string
        containing all of the observations for that work_id.
        """
        oldb = db.get_db()
        data = {
            'username': username,
            'limit': limit,
            'offset': limit * (page - 1)
        }
        query = """
            SELECT
                work_id,
                JSON_AGG(ROW_TO_JSON(
                    (SELECT r FROM
                        (SELECT observation_type, observation_values) r)
                    )
                ) AS observations
            FROM (
                SELECT
                    work_id,
                    observation_type,
                    JSON_AGG(observation_value) AS observation_values
                FROM observations
                WHERE username=$username
                GROUP BY work_id, observation_type) s
            GROUP BY work_id
            LIMIT $limit OFFSET $offset
        """

        return list(oldb.query(query, vars=data))

    def get_multi_choice(type):
        """Searches for the given type in the observations object, and
        returns the type's 'multi_choice' value.

        return: The multi_choice value for the given type

        """
        for o in OBSERVATIONS['observations']:
            if o['label'] == type:
                return o['multi_choice']

    @classmethod
    def persist_observation(
            cls, username, work_id, observation, action,
            edition_id=NULL_EDITION_VALUE):
        """Inserts or deletes a single observation, depending on the given action.

        If the action is 'delete', the observation will be deleted
        from the observations table.

        If the action is 'add', and the observation type only allows a
        single value (multi_choice == True), an attempt is made to
        delete previous observations of the same type before the new
        observation is persisted.

        Otherwise, the new observation is stored in the DB.

        """

        def get_observation_ids(observation):
            """
            Given an observation key-value pair, returns an ObservationIds tuple.

            return: An ObservationsIds tuple
            """
            key = list(observation)[0]
            item = next((o for o in OBSERVATIONS['observations'] if o['label'] == key))

            return ObservationIds(
                item['id'],
                next((v['id'] for v in item['values'] if v['name'] == observation[key]))
            )

        oldb = db.get_db()
        observation_ids = get_observation_ids(observation)

        data = {
            'username': username,
            'work_id': work_id,
            'edition_id': edition_id,
            'observation_type': observation_ids.type_id,
            'observation_value': observation_ids.value_id
        }

        where_clause = 'username=$username AND work_id=$work_id AND observation_type=$observation_type '


        if action == 'delete':
            # Delete observation and return:
            where_clause += 'AND observation_value=$observation_value'

            return oldb.delete(
                'observations',
                vars=data,
                where=where_clause
            )
        elif not cls.get_multi_choice(list(observation)[0]):
            # A radio button value has changed.  Delete old value, if one exists:
            oldb.delete(
                'observations',
                vars=data,
                where=where_clause
            )

        # Insert new value and return:
        return oldb.insert(
            'observations',
            username=username,
            work_id=work_id,
            edition_id=edition_id,
            observation_type=observation_ids.type_id,
            observation_value=observation_ids.value_id
        )

    @classmethod
    def remove_observations(
            cls, username, work_id, edition_id=NULL_EDITION_VALUE,
            observation_type=None, observation_value=None):
        """Deletes observations from the observations table.  If both
        observation_type and observation_value are passed, only one
        row will be deleted from the table.  Otherwise, all of a
        patron's observations for an edition are deleted.

        return: A list of deleted rows.

        """
        oldb = db.get_db()
        data = {
            'username': username,
            'work_id': work_id,
            'edition_id': edition_id,
            'observation_type': observation_type,
            'observation_value': observation_value
        }

        where_clause = 'username=$username AND work_id=$work_id AND edition_id=$edition_id'
        if observation_type and observation_value:
            where_clause += ' AND observation_type=$observation_type AND observation_value=$observation_value'

        return oldb.delete(
            'observations',
            where=(where_clause),
            vars=data
        )
