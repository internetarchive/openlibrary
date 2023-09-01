"""
The purpose of this file is to interact with postgres in relation to Wikidata.
"""

from datetime import datetime
import json
from openlibrary.core import db


class WikidataRow:
    id: str
    data: dict
    updated: datetime


class WikidataEntities(db.CommonExtras):
    TABLENAME = "wikidata"

    @classmethod
    def get_by_id(cls, id) -> WikidataRow | None:
        if len(result := cls.get_by_ids([id])) > 0:
            return result[0]
        return None

    @classmethod
    def get_by_ids(cls, ids: list[str]) -> list[WikidataRow]:
        oldb = db.get_db()
        query = 'select * from wikidata where id IN ($ids)'
        return list(oldb.query(query, vars={'ids': ids}))

    @classmethod
    def add(cls, id: str, data: dict) -> None:
        # TODO: when we upgrade to postgres 9.5+ we should use upsert here
        oldb = db.get_db()
        json_data = json.dumps(data)

        if cls.get_by_id(id) is None:
            return oldb.insert(cls.TABLENAME, id=id, data=json_data)
        else:
            where = "id=$id"
            return oldb.update(cls.TABLENAME, where=where, id=id, data=json_data)
