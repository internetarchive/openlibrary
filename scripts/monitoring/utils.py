import fnmatch
import os
import subprocess
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler


def bash_run(cmd: str, sources: list[str | Path] | None = None, capture_output=False):
    if not sources:
        sources = []

    source_paths = [
        (
            os.path.join("scripts", "monitoring", source)
            if not os.path.isabs(source)
            else source
        )
        for source in sources
    ]
    bash_command = "\n".join(
        (
            'set -e',
            *(f'source "{path}"' for path in source_paths),
            cmd,
        )
    )

    return subprocess.run(
        [
            "bash",
            "-c",
            bash_command,
        ],
        check=True,
        # Mainly for testing:
        capture_output=capture_output,
        text=capture_output or None,
    )


def limit_server(allowed_servers: list[str], scheduler: AsyncIOScheduler):
    """
    Decorate that un-registers a job if the server does not match any of the allowed servers.

    :param allowed_servers: List of allowed servers. Can include `*` for globbing, eg "ol-web*"
    """

    def decorator(func):
        hostname = os.environ.get("HOSTNAME")
        assert hostname
        server = hostname
        if hostname.endswith(".us.archive.org"):
            server = hostname.split(".")[0]

        if not any(fnmatch.fnmatch(server, pattern) for pattern in allowed_servers):
            scheduler.remove_job(func.__name__)
        return func

    return decorator


def get_service_ip(image_name: str) -> str:
    """
    Get the IP address of a Docker image.

    :param image_name: The name of the Docker image.
    :return: The IP address of the Docker image.
    """
    if '-' not in image_name:
        image_name = f'openlibrary-{image_name}-1'

    result = subprocess.run(
        [
            "docker",
            "inspect",
            "-f",
            "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
            image_name,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def assign_stable_ids[T](
    items_sorted: list[T], previous_id_map: dict[T, int]
) -> dict[T, int]:
    """
    Assign stable integer IDs to items, recycling freed IDs (lowest first)
    before minting new ones above the current maximum.

    sorted_items: all current items in desired ID-assignment order
    previous_ids: previously persisted {item: id} mapping (pass {} for first run)
    Returns:      updated {item: id} mapping (only for items in sorted_items)
    """
    items_set = set(items_sorted)
    freed_ids = sorted(v for k, v in previous_id_map.items() if k not in items_set)
    persisted = {k: v for k, v in previous_id_map.items() if k in items_set}
    new_items = [item for item in items_sorted if item not in previous_id_map]
    max_id = max(persisted.values(), default=0)
    freed_iter = iter(freed_ids)
    next_new_id = max_id + 1
    for item in new_items:
        try:
            persisted[item] = next(freed_iter)
        except StopIteration:
            persisted[item] = next_new_id
            next_new_id += 1
    return persisted
