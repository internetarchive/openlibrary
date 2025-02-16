import asyncio
import json
from asyncio import Future
from typing import Literal

import httpx

from openlibrary.solr.utils import solr_insert_documents, str_to_key
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI
from scripts.solr_builder.solr_builder.solr_builder import safeget


def subject_name_to_key(
    subject_type: Literal['subject', 'person', 'place', 'time'], subject_name: str
) -> str:
    escaped_subject_name = str_to_key(subject_name)
    if subject_type == 'subject':
        return f"/subjects/{escaped_subject_name}"
    else:
        return f"/subjects/{subject_type}:{escaped_subject_name}"


def build_subject_doc(
    subject_type: Literal['subject', 'person', 'place', 'time'],
    subject_name: str,
    work_count: int,
):
    """Build the `type:subject` solr doc for this subject."""
    return {
        'key': subject_name_to_key(subject_type, subject_name),
        'name': subject_name,
        'type': 'subject',
        'subject_type': subject_type,
        'work_count': work_count,
    }


async def index_subjects(
    subject_type: Literal['subject', 'person', 'place', 'time'],
    offset=0,
    limit=1,
    solr_base_url='http://solr:8983/solr/openlibrary',
    skip_id_check=False,
):
    """
    :return: Returns number of rows added
    """
    print(json.dumps({'event': 'starting', 'offset': offset}))
    async with httpx.AsyncClient() as client:
        resp = (
            await client.get(
                f'{solr_base_url}/select',
                # Can be slow since we require such a large facet in a chunk
                timeout=180,
                params={
                    'q': 'type:work',
                    'rows': 0,
                    'facet': 'true',
                    'facet.field': f'{subject_type}_facet',
                    'facet.limit': limit,
                    'facet.offset': offset,
                    'facet.sort': 'index',
                    'facet.mincount': 1,
                    'wt': 'json',
                    'json.nl': 'arrarr',
                },
            )
        ).json()
    facets = resp['facet_counts']['facet_fields'][f'{subject_type}_facet']
    docs = [
        build_subject_doc(subject_type, subject_name, work_count)
        for [subject_name, work_count] in facets
    ]

    await solr_insert_documents(
        docs,
        solr_base_url=solr_base_url,
        skip_id_check=skip_id_check,
    )
    print(
        json.dumps(
            {
                'event': 'completed',
                'offset': offset,
                'count': len(docs),
                'first': safeget(lambda: facets[0][0]),
            }
        )
    )
    return len(docs)


async def index_all_subjects(
    subject_type: Literal['subject', 'person', 'place', 'time'],
    chunk_size=10_000,
    instances=2,
    solr_base_url='http://solr:8983/solr/openlibrary',
    skip_id_check=False,
):
    done = False
    active_workers: set[Future] = set()
    offset = 0
    while True:
        if done:
            # Done! Wait for any previous workers that are still going
            await asyncio.gather(*active_workers)
            break
        elif len(active_workers) >= instances:
            # Too many running; wait for one to finish
            finished, pending = await asyncio.wait(
                active_workers, return_when=asyncio.FIRST_COMPLETED
            )
            active_workers = pending
            done = any(task.result() < chunk_size for task in finished)
        else:
            # Can start another worker
            task = asyncio.create_task(
                index_subjects(
                    subject_type,
                    offset=offset,
                    limit=chunk_size,
                    solr_base_url=solr_base_url,
                    skip_id_check=skip_id_check,
                )
            )
            active_workers.add(task)
            offset += chunk_size


if __name__ == '__main__':
    cli = FnToCLI(index_all_subjects)
    print(cli.parse_args())
    cli.run()
