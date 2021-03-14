"""Module for handling patron observation functionality"""

import json
import requests

from infogami import config
from openlibrary import accounts

from . import cache
from . import db

# URL for TheBestBookOn
TBBO_URL = config.get('tbbo_url')

def post_observation(data, s3_keys):
    headers = {
        'x-s3-access': s3_keys['access'],
        'x-s3-secret': s3_keys['secret']
    }

    response = requests.post(TBBO_URL + '/api/observations', data=data, headers=headers)

    return response.text

@cache.memoize(engine="memcache", key="tbbo_aspects", expires=config.get('tbbo_aspect_cache_duration'))
def get_aspects():
    response = requests.get(TBBO_URL + '/api/aspects')

    return response.text

class Observations(object):

    NULL_EDITION_VALUE = -1

    # TODO: Cache these results
    @classmethod
    def get_observation_types_and_values(cls):
        """
        Fetches all observation types, their descriptions and possible values.

        return: List of observation type data.
        """
        oldb = db.get_db()
        query = """
            SELECT 
                observation_types.id as type_id, 
                observation_types.type as type,
                observation_types.description as description,
                observation_types.allow_multiple_values as multi_choice,
                observation_values.id as value_id,
                observation_values.value as value
            FROM observation_types
            JOIN observation_values
                ON observation_values.type = observation_types.id"""

        return list(oldb.query(query))

    # TODO: Cache these results
    @classmethod
    def get_observation_dictionary(cls):
        """
        Returns a dictionary of observation types, values, and IDs.  An observation
        type/value tuple is the key, and the ID is the value.

        return: Dictionary of observation types, values, and IDs
        """
        results = {}
        for observation in cls.get_observation_types_and_values:
            results[observation['type'], observation['value']] = observation['value_id']

        return results

    @classmethod
    def get_patron_observations(cls, username, work_id=None):
        """
        Gets all of a patron's observations by default.  Returns only the observations for
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
                observation_types.type, 
                observation_values.value,
                observation_values.id
            FROM observations
            JOIN observation_values
                ON observations.observation_id = observation_values.id
            JOIN observation_types 
                ON observation_values.type = observation_types.id
            WHERE observations.username = $username"""
        if work_id:
            query += " AND work_id=$work_id"

        return list(oldb.query(query, vars=data))

    @classmethod
    def persist_observations(cls, username, work_id, observations, edition_id=NULL_EDITION_VALUE):
        """
        Insert or update a collection of observations.  If no records exist
        for the given work_id, new observations are inserted.

        """

        def get_observation_ids(observations):
            """
            Given a list of observation key-value pairs, returns a list of observation IDs.

            return: List of observation IDs
            """
            observation_dict = cls.get_observation_dictionary()
            observation_ids = []

            for observation in observations:
                key = list(observation)[0]
                observation_ids.append(observation_dict[key, observation[key]])

            return observation_ids



        oldb = db.get_db()
        records = cls.get_patron_observations(username, work_id)

        if len(records):
            # Delete values that are in existing records but not in submitted observations
            for record in records:
                if { record['type']: record['value'] } not in observations:
                    observation_id = record['id']
                    cls.remove_observations(username, work_id, edition_id=edition_id, observation_id=observation_id)
                    records.remove(record)

            # If same value exists in both existing records and observations, remove from observations
            for record in record:
                if { record['type']: record['value'] } in observations:
                    observations.remove({ record['type']: record['value'] })
                    
        if len(observations):
            # Insert all remaining observations
            observation_ids = get_observation_ids(observations)

            oldb.multiple_insert('observation', 
                [dict(username=username, work_id=work_id, edition_id=edition_id, observation_id=id) for id in observation_ids]
            )

    @classmethod
    def remove_observations(cls, username, work_id, edition_id=NULL_EDITION_VALUE, observation_id=None):
        """
        Deletes observations from the observations table.  If an observation_id is passed, only one
        row will be deleted from the table.  Otherwise, all of a patron's observations for an edition
        are deleted.

        return: A list of deleted rows.
        """
        oldb = db.get_db()
        data = {
            'username': username,
            'work_id': work_id,
            'edition_id': edition_id,
            'observation_id': observation_id
        }

        where_clause = 'username=$username AND work_id=$work_id AND edition_id=$edition_id'
        if observation_id:
            where_clause += ' AND observation_id=$observation_id'

        return oldb.delete(
            'observations',
            where=(where_clause),
            vars=data
        )
