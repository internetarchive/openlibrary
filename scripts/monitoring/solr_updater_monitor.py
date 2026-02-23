import time
from datetime import datetime

import httpx

from scripts.monitoring.haproxy_monitor import GraphiteEvent
from scripts.monitoring.utils import bash_run


async def get_solr_updater_lag_event(solr_next=False) -> GraphiteEvent:
    service = "solr-updater"
    offset_file = "solr-update.offset"
    bucket = "stats.ol.solr.solr_updater_lag"

    if solr_next:
        service = "solr-next-updater"
        offset_file = "solr-next-update.offset"
        bucket = "stats.ol.solr_next.solr_updater_lag"

    solr_offset = bash_run(
        f"docker exec openlibrary-{service}-1 cat /solr-updater-data/{offset_file}",
        capture_output=True,
    ).stdout.strip()

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f'http://localhost:7000/openlibrary.org/log/{solr_offset}?limit=1'
        )
        data = response.json()
        last_processed_timestamp_str = data['data'][0]['timestamp']

        # Parse ISO format timestamp
        dt = datetime.fromisoformat(last_processed_timestamp_str)
        last_processed_timestamp = int(dt.timestamp())

        now = int(time.time())
        lag_seconds = now - last_processed_timestamp
        return GraphiteEvent(path=bucket, value=lag_seconds, timestamp=now)
