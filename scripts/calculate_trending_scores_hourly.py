import _init_path
import os
from openlibrary.config import load_config
from openlibrary.core import db
from openlibrary.plugins.worksearch.code import get_solr_works


def fetch_works(work_ids: list[int]):
    fields = [f'trending_score_hourly_{index}' for index in range(23)]
    fields.extend([f'trending_score_daily_{index}' for index in range(7)])


def update_hourly_count_and_z_score(work_id: int, count: int):
    pass


if __name__ == '__main__':
    from contextlib import redirect_stdout

    ol_config = os.getenv("OL_CONFIG")
    if ol_config:
        with open(os.devnull, 'w') as devnull, redirect_stdout(devnull):
            load_config(ol_config)
        ol_db = db.get_db()
        query = "select work_id, Count(updated)"
        query += "from bookshelves_events group by bookshelves_events.updated, work_id"
        query += "having updated >= localtimestamp - interval '1 hour'"
        print(ol_db.__dir__())
        ids_needing_changes = list(ol_db.query(query))
        print(ids_needing_changes[0].work_id)
    else:
        print("failure")
