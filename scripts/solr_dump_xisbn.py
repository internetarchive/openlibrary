#!/usr/bin/env python
"""
    Script for creating a file of similar ISBNs or LCCNs from Solr.

    Run on ol-solr1 (the staging solr). Turn off solr-next-updater on
    ol-home0 , to avoid extra strain on the server, and then kick it off with
    `tmux` (use tmux so if the ssh connection disconnects the process continues)

    ```sh
    # Took ~10.5 hours 2024-04
    time docker run --rm \
        --name similarities-dump \
        --network host \
        -e PYTHONPATH=/openlibrary \
        openlibrary/olbase:latest \
        python scripts/solr_dump_xisbn.py --solr-base http://localhost:8983/solr/openlibrary \
    > unwanted_isbns_$(date +"%Y-%m-%d").txt

    # Took ~8.5 hours 2024-04
    time docker run --rm \
        --name similarities-dump \
        --network host \
        -e PYTHONPATH=/openlibrary \
        openlibrary/olbase:latest \
        python scripts/solr_dump_xisbn.py --solr-base http://localhost:8983/solr/openlibrary --id-field lccn \
    > unwanted_lccns_$(date +"%Y-%m-%d").txt
    ```
"""
import asyncio
import sys
from collections.abc import AsyncGenerator
from typing import Literal

import httpx

# EG http://localhost:8984/solr/openlibrary/select?editions.fl=key%2Cisbn&editions.q=(%7B!terms%20f%3D_root_%20v%3D%24row.key%7D)%20AND%20language%3Aeng%20AND%20isbn%3A*%20AND%20type%3Aedition&editions.rows=1000000&fl=key%2Ceditions%3A%5Bsubquery%5D&fq=type%3Awork&indent=true&q=isbn%3A*%20AND%20NOT%20subject%3Atextbook%20AND%20_query_%3A(%7B!parent%20which%3Dtype%3Awork%20v%3D%22language%3Aeng%20AND%20ia_box_id%3A*%22%20filters%3D%22type%3Aedition%22%7D)&sort=key%20asc&wt=json


async def fetch_docs(
    params: dict[str, str | int],
    solr_base: str,
    page_size=100,
) -> list[dict]:
    """Stream results from a Solr query. Uses cursors."""
    params = params.copy()
    params['rows'] = page_size

    async with httpx.AsyncClient() as client:
        for attempt in range(5):
            try:
                response = await client.get(
                    f'{solr_base}/select',
                    params=params,
                    timeout=60,
                )
                response.raise_for_status()
                break
            except (httpx.RequestError, httpx.HTTPStatusError):
                if attempt == 4:
                    raise
                await asyncio.sleep(2)
        data = response.json()
        return data['response']['docs']


async def stream_bounds(
    params: dict[str, str],
    solr_base: str,
    page_size=100,
) -> AsyncGenerator[tuple[str, str], None]:
    """Stream bounds from a Solr query. Uses cursors."""
    params = params.copy()
    params['rows'] = page_size
    params['cursorMark'] = '*'
    numFound = None
    seen = 0

    # Keep session open and retry on connection errors
    transport = httpx.AsyncHTTPTransport()
    async with httpx.AsyncClient(transport=transport) as client:
        while True:
            print(f'FETCH {params["cursorMark"]}', file=sys.stderr)
            if numFound:
                print(f'{seen/numFound=}', file=sys.stderr)

            for attempt in range(5):
                try:
                    response = await client.get(
                        f'{solr_base}/select',
                        params=params,
                        timeout=60,
                    )
                    response.raise_for_status()
                    break
                except (httpx.RequestError, httpx.HTTPStatusError):
                    if attempt == 4:
                        raise
                    await asyncio.sleep(2)
            data = response.json()
            numFound = data['response']['numFound']

            docs = data['response']['docs']
            if docs:
                seen += len(docs)
                yield docs[0]['key'], docs[-1]['key']
            else:
                break

            if params['cursorMark'] == data['nextCursorMark']:
                break
            else:
                params['cursorMark'] = data['nextCursorMark']


async def main(
    solr_base='http://localhost:8984/solr/openlibrary',
    workers=10,
    page_size=100,
    id_field: Literal['isbn', 'lccn'] = 'isbn',
) -> None:
    """
    :param solr_base: Base URL of Solr instance
    :param workers: Number of workers to use
    :param page_size: Number of results to fetch per query
    :param id_field: Which identifier to use for matching
    """
    id_filter = f'{id_field}:*'
    work_exclusions = 'subject:textbook'
    galloping_params = {
        # Find works that have at least one edition with an IA box id
        'q': f"""
            {id_filter}
            AND NOT ({work_exclusions})
            AND _query_:({{!parent which=type:work v="language:eng AND ia_box_id:*" filters="type:edition"}})
        """,
        'fq': 'type:work',
        'sort': 'key asc',
        'fl': 'key',
        'wt': 'json',
    }

    # This is a performance hack
    # this returns pairs like ('/works/OL1W', '/works/OL200W'), ('/works/OL201W', '/works/OL300W')
    # which we can use to make multiple queries in parallel

    # Now create an async worker pool to fetch the actual data
    async def fetch_bounds(bounds):
        print(f'[ ] FETCH {bounds=}', file=sys.stderr)
        start, end = bounds
        result = ''
        for doc in await fetch_docs(
            {
                'q': f'key:["{start}" TO "{end}"] AND {galloping_params["q"]}',
                'fq': 'type:work',
                'fl': 'key,editions:[subquery]',
                'editions.q': f'({{!terms f=_root_ v=$row.key}}) AND language:eng AND {id_filter}',
                'editions.fq': 'type:edition',
                'editions.fl': f'key,{id_field}',
                'editions.rows': 1_000_000,
                'wt': 'json',
            },
            solr_base,
            page_size=page_size * 2,
        ):
            identifiers = {
                identifier
                for ed in doc['editions']['docs']
                for identifier in ed[id_field]
                if (len(identifier) == 13 if id_field == 'isbn' else True)
            }
            if len(identifiers) > 1:
                result += ' '.join(identifiers) + '\n'
        print(f'[x] FETCH {bounds=}', file=sys.stderr)
        if result:
            print(result, flush=True)

    # now run N workers in async pool to process the bounds
    running: set[asyncio.Task] = set()
    async for bounds in stream_bounds(galloping_params, solr_base, page_size=page_size):
        if len(running) >= workers:
            done, running = await asyncio.wait(
                running, return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                task.result()
        running.add(asyncio.create_task(fetch_bounds(bounds)))

    # wait for all workers to finish
    await asyncio.wait(running)


if __name__ == '__main__':
    from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

    FnToCLI(main).run()
