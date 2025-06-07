from . import db


def make_pd_request_query():
    oldb = db.get_db()

    query = """
        WITH pda_key AS (
            SELECT id AS key_id FROM property WHERE name = 'notifications.pda'
        ),
        status_key AS (
            SELECT id AS key_id FROM property WHERE name = 'notifications.rpd'
        ),
        combined AS (
            -- Per-qualifying authority rows
            SELECT
                pda.value AS pda,
                COUNT(CASE WHEN status.value = 0 THEN 1 END) AS requested,
                COUNT(CASE WHEN status.value = 1 THEN 1 END) AS emailed,
                COUNT(CASE WHEN status.value = 2 THEN 1 END) AS fulfilled,
                1 AS sort_order
            FROM
                datum_str AS pda
            JOIN
                datum_int AS status ON pda.thing_id = status.thing_id
            JOIN
                pda_key ON pda.key_id = pda_key.key_id
            JOIN
                status_key ON status.key_id = status_key.key_id
            GROUP BY
                pda.value

            UNION ALL

            -- Total row
            SELECT
                'TOTAL' AS pda,
                COUNT(CASE WHEN status.value = 0 THEN 1 END),
                COUNT(CASE WHEN status.value = 1 THEN 1 END),
                COUNT(CASE WHEN status.value = 2 THEN 1 END),
                0 AS sort_order
            FROM
                datum_str AS pda
            JOIN
                datum_int AS status ON pda.thing_id = status.thing_id
            JOIN
                pda_key ON pda.key_id = pda_key.key_id
            JOIN
                status_key ON status.key_id = status_key.key_id
        )

        SELECT
            pda,
            requested,
            emailed,
            fulfilled
        FROM
            combined
        ORDER BY
            sort_order, pda
    """

    return list(oldb.query(query))
