from . import db

def make_pd_request_query() -> list:
    oldb = db.get_db()

    query = """
        SELECT
            pda.value AS pda,
            COUNT(CASE WHEN status.value = 0 THEN 1 END) AS requested,
            COUNT(CASE WHEN status.value = 1 THEN 1 END) AS emailed,
            COUNT(CASE WHEN status.value = 2 THEN 1 END) AS fulfilled
        FROM
            datum_str AS pda
        JOIN
            datum_int AS status
            ON pda.thing_id = status.thing_id
        WHERE
            pda.key_id = (SELECT id FROM property WHERE name = 'notifications.pda')
            AND status.key_id = (SELECT id FROM property WHERE name = 'notifications.rpd')
        GROUP BY
            pda.value;
    """

    return list(oldb.query(query))
