"""Module for handling patron observation functionality"""

from collections import defaultdict, namedtuple

from infogami import config
from infogami.utils.view import public
from openlibrary import accounts
from openlibrary.utils import extract_numeric_id_from_olid

from . import cache
from . import db

ObservationIds = namedtuple('ObservationIds', ['type_id', 'value_id'])
ObservationKeyValue = namedtuple('ObservationKeyValue', ['key', 'value'])

OBSERVATIONS = {
    'observations': [
        {
            'id': 1,
            'label': 'pace',
            'description': 'How would you rate the pacing of this book?',
            'multi_choice': True,
            'order': [4, 5, 6, 7],
            'values': [
                {'id': 1, 'name': 'slow', 'deleted': True},
                {'id': 2, 'name': 'medium', 'deleted': True},
                {'id': 3, 'name': 'fast', 'deleted': True},
                {'id': 4, 'name': 'too slow'},
                {'id': 5, 'name': 'well paced'},
                {'id': 6, 'name': 'too fast'},
                {'id': 7, 'name': 'meandering'},
            ]
        },
        {
            'id': 2,
            'label': 'enjoyability',
            'description': 'How much did you enjoy reading this book?',
            'multi_choice': True,
            'order': [3, 7, 8, 9],
            'values': [
                {'id': 1, 'name': 'not applicable', 'deleted': True},
                {'id': 2, 'name': 'very boring', 'deleted': True},
                {'id': 4, 'name': 'neither entertaining nor boring', 'deleted': True},
                {'id': 5, 'name': 'entertaining', 'deleted': True},
                {'id': 6, 'name': 'very entertaining', 'deleted': True},
                {'id': 3, 'name': 'boring'},
                {'id': 7, 'name': 'engaging'},
                {'id': 8, 'name': 'exciting'},
                {'id': 9, 'name': 'neutral'},
            ],
        },
        {
            'id': 3,
            'label': 'clarity',
            'description': 'How clearly was this book written and presented?',
            'multi_choice': True,
            'order': [6, 7, 8, 9, 10, 11, 12, 13],
            'values': [
                {'id': 1, 'name': 'not applicable', 'deleted': True},
                {'id': 2, 'name': 'very unclearly', 'deleted': True},
                {'id': 3, 'name': 'unclearly', 'deleted': True},
                {'id': 4, 'name': 'clearly', 'deleted': True},
                {'id': 5, 'name': 'very clearly', 'deleted': True},
                {'id': 6, 'name': 'succinct'},
                {'id': 7, 'name': 'dense'},
                {'id': 8, 'name': 'incomprehensible'},
                {'id': 9, 'name': 'confusing'},
                {'id': 10, 'name': 'clearly written'},
                {'id': 11, 'name': 'effective explanations'},
                {'id': 12, 'name': 'well organized'},
                {'id': 13, 'name': 'disorganized'},
            ],
        },
        {
            'id': 4,
            'label': 'jargon',
            'description': 'How technical is the content?',
            'multi_choice': False,
            'order': [1, 2, 3, 4, 5],
            'values': [
                {'id': 1, 'name': 'not applicable'},
                {'id': 2, 'name': 'not technical'},
                {'id': 3, 'name': 'somewhat technical'},
                {'id': 4, 'name': 'technical'},
                {'id': 5, 'name': 'very technical'}
            ],
            'deleted': True
        },
        {
            'id': 5,
            'label': 'originality',
            'description': 'How original is this book?',
            'multi_choice': False,
            'order': [1, 2, 3, 4, 5],
            'values': [
                {'id': 1, 'name': 'not applicable'},
                {'id': 2, 'name': 'very unoriginal'},
                {'id': 3, 'name': 'somewhat unoriginal'},
                {'id': 4, 'name': 'somewhat original'},
                {'id': 5, 'name': 'very original'}
            ],
            'deleted': True
        },
        {
            'id': 6,
            'label': 'difficulty',
            'description': 'How would you rate the difficulty of '
                           'this book for a general audience?',
            'multi_choice': True,
            'order': [6, 7, 8, 9, 10, 11, 12],
            'values': [
                {'id': 1, 'name': 'not applicable', 'deleted': True},
                {'id': 2, 'name': 'requires domain expertise', 'deleted': True},
                {'id': 3, 'name': 'a lot of prior knowledge needed', 'deleted': True},
                {'id': 4, 'name': 'some prior knowledge needed', 'deleted': True},
                {'id': 5, 'name': 'no prior knowledge needed', 'deleted': True},
                {'id': 6, 'name': 'beginner'},
                {'id': 7, 'name': 'intermediate'},
                {'id': 8, 'name': 'advanced'},
                {'id': 9, 'name': 'expert'},
                {'id': 10, 'name': 'university'},
                {'id': 11, 'name': 'layman'},
                {'id': 12, 'name': 'juvenile'},
            ],
        },
        {
            'id': 7,
            'label': 'usefulness',
            'description': 'How useful is the content of this book?',
            'multi_choice': False,
            'order': [1, 2, 3, 4, 5],
            'values': [
                {'id': 1, 'name': 'not applicable'},
                {'id': 2, 'name': 'not useful'},
                {'id': 3, 'name': 'somewhat useful'},
                {'id': 4, 'name': 'useful'},
                {'id': 5, 'name': 'very useful'}
            ],
            'deleted': True
        },
        {
            'id': 8,
            'label': 'coverage',
            'description': "How would you describe the breadth and depth of this book?",
            'multi_choice': True,
            'order': [7, 8, 9, 10, 11, 12, 13],
            'values': [
                {'id': 1, 'name': 'not applicable', 'deleted': True},
                {'id': 2, 'name': 'much more deep', 'deleted': True},
                {'id': 3, 'name': 'somewhat more deep', 'deleted': True},
                {'id': 4, 'name': 'equally broad and deep', 'deleted': True},
                {'id': 5, 'name': 'somewhat more broad', 'deleted': True},
                {'id': 6, 'name': 'much more broad', 'deleted': True},
                {'id': 7, 'name': 'comprehensive'},
                {'id': 8, 'name': 'not comprehensive'},
                {'id': 9, 'name': 'focused'},
                {'id': 10, 'name': 'interdisciplinary'},
                {'id': 11, 'name': 'extraneous'},
                {'id': 12, 'name': 'shallow'},
                {'id': 13, 'name': 'introductory'},
            ],
        },
        {
            'id': 9,
            'label': 'objectivity',
            'description': 'Are there causes to question the accuracy of this book?',
            'multi_choice': True,
            'order': [1, 2, 3, 4, 5, 6, 7, 8],
            'values': [
                {'id': 1, 'name': 'not applicable'},
                {'id': 2, 'name': 'no, it seems accurate'},
                {'id': 3, 'name': 'yes, it needs citations'},
                {'id': 4, 'name': 'yes, it is inflammatory'},
                {'id': 5, 'name': 'yes, it has typos'},
                {'id': 6, 'name': 'yes, it is inaccurate'},
                {'id': 7, 'name': 'yes, it is misleading'},
                {'id': 8, 'name': 'yes, it is biased'}
            ],
            'deleted': True
        },
        {
            'id': 10,
            'label': 'genres',
            'description': 'What are the genres of this book?',
            'multi_choice': True,
            'order': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24],
            'values': [
                {'id': 1, 'name': 'sci-fi'},
                {'id': 2, 'name': 'philosophy', 'deleted': True},
                {'id': 3, 'name': 'satire'},
                {'id': 4, 'name': 'poetry'},
                {'id': 5, 'name': 'memoir'},
                {'id': 6, 'name': 'paranormal'},
                {'id': 7, 'name': 'mystery'},
                {'id': 8, 'name': 'humor'},
                {'id': 9, 'name': 'horror'},
                {'id': 10, 'name': 'fantasy'},
                {'id': 11, 'name': 'drama'},
                {'id': 12, 'name': 'crime'},
                {'id': 13, 'name': 'graphical'},
                {'id': 14, 'name': 'classic'},
                {'id': 15, 'name': 'anthology'},
                {'id': 16, 'name': 'action'},
                {'id': 17, 'name': 'romance'},
                {'id': 18, 'name': 'how-to'},
                {'id': 19, 'name': 'encyclopedia'},
                {'id': 20, 'name': 'dictionary'},
                {'id': 21, 'name': 'technical'},
                {'id': 22, 'name': 'reference'},
                {'id': 23, 'name': 'textbook'},
                {'id': 24, 'name': 'biographical'},
            ]
        },
        {
            'id': 11,
            'label': 'fictionality',
            'description': "Is this book a work of fact or fiction?",
            'multi_choice': False,
            'order': [1, 2, 3],
            'values': [
                {'id': 1, 'name': 'nonfiction'},
                {'id': 2, 'name': 'fiction'},
                {'id': 3, 'name': 'biography'}
            ],
            'deleted': True
        },
        {
            'id': 12,
            'label': 'audience',
            'description': "What are the intended age groups for this book?",
            'multi_choice': True,
            'order': [1, 2, 3, 4, 5, 6, 7],
            'values': [
                {'id': 1, 'name': 'experts'},
                {'id': 2, 'name': 'college'},
                {'id': 3, 'name': 'high school'},
                {'id': 4, 'name': 'elementary'},
                {'id': 5, 'name': 'kindergarten'},
                {'id': 6, 'name': 'baby'},
                {'id': 7, 'name': 'general audiences'}
            ],
            'deleted': True
        },
        {
            'id': 13,
            'label': 'mood',
            'description': 'What are the moods of this book?',
            'multi_choice': True,
            'order': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26],
            'values': [
                {'id': 1, 'name': 'scientific'},
                {'id': 2, 'name': 'dry'},
                {'id': 3, 'name': 'emotional'},
                {'id': 4, 'name': 'strange'},
                {'id': 5, 'name': 'suspenseful'},
                {'id': 6, 'name': 'sad'},
                {'id': 7, 'name': 'dark'},
                {'id': 8, 'name': 'lonely'},
                {'id': 9, 'name': 'tense'},
                {'id': 10, 'name': 'fearful'},
                {'id': 11, 'name': 'angry'},
                {'id': 12, 'name': 'hopeful'},
                {'id': 13, 'name': 'lighthearted'},
                {'id': 14, 'name': 'calm'},
                {'id': 15, 'name': 'informative'},
                {'id': 16, 'name': 'ominous'},
                {'id': 17, 'name': 'mysterious'},
                {'id': 18, 'name': 'romantic'},
                {'id': 19, 'name': 'whimsical'},
                {'id': 20, 'name': 'idyllic'},
                {'id': 21, 'name': 'melancholy'},
                {'id': 22, 'name': 'humorous'},
                {'id': 23, 'name': 'gloomy'},
                {'id': 24, 'name': 'reflective'},
                {'id': 25, 'name': 'inspiring'},
                {'id': 26, 'name': 'cheerful'},
            ]
        },
        {
            'id': 14,
            'label': 'endorsements',
            'description': 'How did you feel about this book and do you recommend it?',
            'multi_choice': True,
            'order': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14],
            'values': [
                {'id': 1, 'name': 'recommend'},
                {'id': 2, 'name': 'highly recommend'},
                {'id': 3, 'name': "don't recommend"},
                {'id': 4, 'name': 'field defining'},
                {'id': 5, 'name': 'actionable'},
                {'id': 6, 'name': 'forgettable'},
                {'id': 7, 'name': 'quotable'},
                {'id': 8, 'name': 'citable'},
                {'id': 9, 'name': 'original'},
                {'id': 10, 'name': 'unremarkable'},
                {'id': 11, 'name': 'life changing'},
                {'id': 12, 'name': 'best in class'},
                {'id': 13, 'name': 'overhyped'},
                {'id': 14, 'name': 'underrated'},
            ]
        },
        {
            'id': 15,
            'label': 'type',
            'description': 'How would you classify this work?',
            'multi_choice': True,
            'order': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13],
            'values': [
                {'id': 1, 'name': 'fiction'},
                {'id': 2, 'name': 'nonfiction'},
                {'id': 3, 'name': 'biography'},
                {'id': 4, 'name': 'based on a true story'},
                {'id': 5, 'name': 'textbook'},
                {'id': 6, 'name': 'reference'},
                {'id': 7, 'name': 'exploratory'},
                {'id': 8, 'name': 'research'},
                {'id': 9, 'name': 'philosophical'},
                {'id': 10, 'name': 'biography'},
                {'id': 11, 'name': 'essay'},
                {'id': 12, 'name': 'review'},
                {'id': 13, 'name': 'classic'},
            ]
        },
        {
            'id': 16,
            'label': 'length',
            'description': 'How would you rate or describe the length of this book?',
            'multi_choice': True,
            'order': [1, 2, 3],
            'values': [
                {'id': 1, 'name': 'too short'},
                {'id': 2, 'name': 'ideal length'},
                {'id': 3, 'name': 'too long'},
            ]
        },
        {
            'id': 17,
            'label': 'credibility',
            'description': 'How factually accurate and reliable '
                           'is the content of this book?',
            'multi_choice': True,
            'order': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
            'values': [
                {'id': 1, 'name': 'accurate'},
                {'id': 2, 'name': 'inaccurate'},
                {'id': 3, 'name': 'outdated'},
                {'id': 4, 'name': 'evergreen'},
                {'id': 5, 'name': 'biased'},
                {'id': 6, 'name': 'objective'},
                {'id': 7, 'name': 'subjective'},
                {'id': 8, 'name': 'rigorous'},
                {'id': 9, 'name': 'misleading'},
                {'id': 10, 'name': 'controversial'},
                {'id': 11, 'name': 'trendy'},
            ]
        },
        {
            'id': 18,
            'label': 'formatting',
            'description': 'What types of formatting or structure '
                           'does this book make use of?',
            'multi_choice': True,
            'order': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
            'values': [
                {'id': 1, 'name': 'tables, diagrams, and figures'},
                {'id': 2, 'name': 'problem sets'},
                {'id': 3, 'name': 'proofs'},
                {'id': 4, 'name': 'interviews'},
                {'id': 5, 'name': 'table of contents'},
                {'id': 6, 'name': 'illustrations'},
                {'id': 7, 'name': 'index'},
                {'id': 8, 'name': 'glossary'},
                {'id': 9, 'name': 'chapters'},
                {'id': 10, 'name': 'appendix'},
                {'id': 11, 'name': 'bibliography'},
            ]
        },
        {
            'id': 19,
            'label': 'content advisories',
            'description': 'Does this book contain objectionable content?',
            'multi_choice': True,
            'order': [1, 2, 3, 4, 5, 6],
            'values': [
                {'id': 1, 'name': 'adult themes'},
                {'id': 2, 'name': 'trigger warnings'},
                {'id': 3, 'name': 'offensive language'},
                {'id': 4, 'name': 'graphic imagery'},
                {'id': 5, 'name': 'insensitive'},
                {'id': 6, 'name': 'racism'},
            ]
        },
        {
            'id': 20,
            'label': 'language',
            'description': 'What type of verbiage, nomenclature, '
                           'or symbols are employed in this book?',
            'multi_choice': True,
            'order': [1, 2, 3, 4, 5],
            'values': [
                {'id': 1, 'name': 'technical'},
                {'id': 2, 'name': 'jargony'},
                {'id': 3, 'name': 'neologisms'},
                {'id': 4, 'name': 'slang'},
                {'id': 5, 'name': 'olde'},
            ]
        },
        {
            'id': 21,
            'label': 'purpose',
            'description': 'Why should someone read this book?',
            'multi_choice': True,
            'order': [1, 2, 3, 4, 5, 6, 7, 8, 9],
            'values': [
                {'id': 1, 'name': 'entertainment'},
                {'id': 2, 'name': 'broaden perspective'},
                {'id': 3, 'name': 'how-to'},
                {'id': 4, 'name': 'learn about'},
                {'id': 5, 'name': 'self-help'},
                {'id': 6, 'name': 'hope'},
                {'id': 7, 'name': 'inspiration'},
                {'id': 8, 'name': 'fact checking'},
                {'id': 9, 'name': 'problem solving'},
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
                'description': 'What is the pace of this book?' 
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
        value = next((v['name'] for v in values_list 
                if v['id'] == id and not v.get('deleted', False)), None
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

        current_type_id = observation_totals[0]['type_id']
        observation_item = next((o for o in OBSERVATIONS['observations'] if current_type_id == o['id']))

        current_observation = {
            'label': observation_item['label'],
            'description': observation_item['description'],
            'multi_choice': observation_item['multi_choice'],
            'total_respondents_for_type': respondents_per_type_dict[current_type_id],
            'values': []
        }

        for i in observation_totals:
            if i['type_id'] != current_type_id:
                metrics['observations'].append(current_observation)
                current_type_id = i['type_id']
                observation_item = next((o for o in OBSERVATIONS['observations'] if current_type_id == o['id']))
                current_observation = {
                    'label': observation_item['label'],
                    'description': observation_item['description'],
                    'multi_choice': observation_item['multi_choice'],
                    'total_respondents_for_type': respondents_per_type_dict[current_type_id],
                    'values': []
                }
            current_observation['values'].append(
                    { 
                        'value': next((v['name'] for v in observation_item['values'] if v['id'] == i['value_id'])), 
                        'count': i['total'] 
                    } 
                )
    
        metrics['observations'].append(current_observation)
    return metrics
        

class Observations(object):

    NULL_EDITION_VALUE = -1

    @classmethod
    def total_unique_respondents(cls, work_id=None):
        """
        Returns total number of patrons who have submitted observations for the given work ID.
        If no work ID is passed, returns total number of patrons who have submitted observations
        for any work.

        return: Total number of patrons who have made an observation.
        """
        oldb = db.get_db()
        data = {
            'work_id': work_id
        }
        query = "SELECT COUNT(DISTINCT(username)) FROM observations"

        if work_id:
            query += " WHERE work_id = $work_id"

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
            'work_id': work_id
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
        """
        Searches for the given type in the observations object, and returns the type's 'multi_choice' value.

        return: The multi_choice value for the given type
        """
        for o in OBSERVATIONS['observations']:
            if o['label'] == type:
                return o['multi_choice']

    @classmethod
    def persist_observation(cls, username, work_id, observation, action, edition_id=NULL_EDITION_VALUE):
        """
        Inserts or deletes a single observation, depending on the given action.

        If the action is 'delete', the observation will be deleted from the observations table.

        If the action is 'add', and the observation type only allows a single value (multi_choice == True), 
        an attempt is made to delete previous observations of the same type before the new observation is 
        persisted.

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
    def remove_observations(cls, username, work_id, edition_id=NULL_EDITION_VALUE, observation_type=None, observation_value=None):
        """
        Deletes observations from the observations table.  If both observation_type and observation_value are
        passed, only one row will be deleted from the table.  Otherwise, all of a patron's observations for an edition
        are deleted.

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
