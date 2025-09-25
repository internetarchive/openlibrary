import time
from datetime import datetime

import httpx

from scripts.monitoring.haproxy_monitor import GraphiteEvent
from scripts.monitoring.utils import bash_run


async def monitor_solr_updater(
    solr_next: bool = False,
    dry_run: bool = False,
):
    if solr_next:
        offset_file = '/solr-updater-data/solr-next-update.offset'
        container_name = 'openlibrary-solr-next-updater-1'
        bucket = 'stats.ol.solr-next-updater'
    else:
        offset_file = '/solr-updater-data/solr-update.offset'
        container_name = 'openlibrary-solr-updater-1'
        bucket = 'stats.ol.solr-updater'

    # Check if container running
    docker_ps = bash_run("docker ps --format '{{.Names}}'", capture_output=True)
    if container_name not in docker_ps.splitlines():
        print(f"[OL-MONITOR] Container {container_name} not running.", flush=True)
        return

    solr_offset = bash_run(
        # Note they share a volume mount, so can exec into either container to read
        # the offset file.
        f'docker exec openlibrary-solr-updater-1 cat {offset_file}',
        capture_output=True,
    )

    async with httpx.AsyncClient() as client:
        response = await client.get(
            # Note have to access infobase via ol-home to avoid circular routing
            # issues in docker network.
            f"http://ol-home.us.archive.org:7000/openlibrary.org/log/{solr_offset}?limit=1"
        )
        response.raise_for_status()
        data = response.json()
        if not data["data"]:
            print(
                "[OL-MONITOR] No data returned from solr-updater log endpoint.",
                flush=True,
            )
            return

        # e.g. 2025-09-20T03:40:33.670905
        timestamp = data["data"][0]["timestamp"]
        timestamp_parsed = datetime.fromisoformat(timestamp)
        now = time.time()
        elapsed_seconds = int(now - timestamp_parsed.timestamp())

        event = GraphiteEvent(
            path=f"{bucket}.seconds_behind",
            value=elapsed_seconds,
            timestamp=int(now),
        )
        print(event.serialize_str())
        if not dry_run:
            event.submit('graphite.us.archive.org:2004')


if __name__ == "__main__":
    from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

    FnToCLI(monitor_solr_updater).run()
