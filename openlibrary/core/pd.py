from . import db


def make_pd_request_query():
    oldb = db.get_db()

    query = """
        SELECT
            pda.value AS qualifying_org,
            COUNT(CASE WHEN rpd.value = '0' THEN 1 END) AS requested,
            COUNT(CASE WHEN rpd.value = '1' THEN 1 END) AS emailed,
            COUNT(CASE WHEN rpd.value = '2' THEN 1 END) AS fulfilled
        FROM store_index pda
        JOIN store_index rpd
            ON pda.store_id = rpd.store_id
           AND rpd.type = 'preferences'
           AND rpd.name = 'rpd'
        WHERE pda.type = 'preferences'
          AND pda.name = 'pda'
        GROUP BY pda.value
        ORDER BY pda.value
    """

    return list(oldb.query(query))
