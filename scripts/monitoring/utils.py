import fnmatch
import os
import subprocess

from apscheduler.schedulers.asyncio import AsyncIOScheduler


def bash_run(cmd: str, sources: list[str] | None = None, capture_output=False):
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
        text=capture_output if capture_output else None,
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
