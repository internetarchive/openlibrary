from openlibrary.core import db


class WikidataEntities(db.CommonExtras):
    TABLENAME = "wikidata"
    PRIMARY_KEY = "id"

    @classmethod
    def get_by_id(cls, id) -> dict | None:
        result = cls.get_by_ids([id])
        if len(result) > 0:
            return result[0]
        return None

    @classmethod
    def get_by_ids(cls, ids: list[str]) -> list:  # TODO typing??...
        oldb = db.get_db()
        query = 'select * from wikidata where id IN ($ids)'
        return list(oldb.query(query, vars={'ids': ids}))

    @classmethod
    def add(cls, id: str, data: dict) -> None:
        oldb = db.get_db()

        wikidata_entities = cls.get_by_ids([id])
        if len(wikidata_entities) == 0:
            return oldb.insert(cls.TABLENAME, id=id, data=data)
        else:
            where = "id=$id"
            return oldb.update(cls.TABLENAME, where=where, id=id, data=data)
