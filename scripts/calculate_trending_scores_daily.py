import _init_path
import os
from openlibrary.config import load_config
from openlibrary.core import db
from openlibrary.plugins.worksearch.code import execute_solr_query
import datetime

from openlibrary.plugins.worksearch.search import get_solr


def fetch_works(current_day: int):
    resp = execute_solr_query(
        '/export',
        {
            "q": f'trending_score_hourly_sum:[1 TO *] OR trending_score_daily_{current_day}:[1 TO *]',
            "fl": "key,trending_score_hourly_sum",
            "sort": "trending_score_hourly_sum desc",
        },
    )
    doc_data = {}
    if resp:
        data = resp.json()
        try:
            docs = data["response"]["docs"]
        except KeyError:
            raise KeyError
        print(docs)
        doc_data = {doc["key"]: doc.get("trending_score_hourly_sum", 0) for doc in docs}
    return doc_data


def form_inplace_updates(work_id: str, current_day: int, new_value: int):
    return {"key": work_id, f'trending_score_daily_{current_day}': {"set": new_value}}


if __name__ == '__main__':
    from contextlib import redirect_stdout

    ol_config = os.getenv("OL_CONFIG")
    if ol_config:
        with open(os.devnull, 'w') as devnull, redirect_stdout(devnull):
            load_config(ol_config)
    current_day = datetime.datetime.now().weekday()
    work_data = fetch_works(current_day)

    request_body = [
        form_inplace_updates(work_id, current_day, work_data[work_id])
        for work_id in work_data
    ]

    resp = get_solr().update_in_place(request_body)
