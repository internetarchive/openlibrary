import datetime

import _init_path  # noqa: F401 Imported for its side effect of setting PYTHONPATH

from openlibrary.config import load_config
from openlibrary.plugins.worksearch.code import execute_solr_query
from openlibrary.plugins.worksearch.search import get_solr
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI


def fetch_works_trending_scores(current_day: int):
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


def main(openlibrary_yml: str):
    if openlibrary_yml:
        load_config(openlibrary_yml)
        current_day = datetime.datetime.now().weekday()
        work_data = fetch_works_trending_scores(current_day)

        request_body = [
            form_inplace_updates(work_id, current_day, work_data[work_id])
            for work_id in work_data
        ]
        print("Daily update completed.")

        resp = get_solr().update_in_place(request_body, commit=True)
    else:
        print("Error: OL_Config could not be found.")


if __name__ == '__main__':
    FnToCLI(main).run()
