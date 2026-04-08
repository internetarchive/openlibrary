import fnmatch
import os
import pickle
import socket
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from apscheduler.schedulers.asyncio import AsyncIOScheduler


@dataclass
class GraphiteEvent:
    path: str
    value: float
    timestamp: int

    def serialize(self):
        return (self.path, (self.timestamp, self.value))

    def serialize_str(self) -> str:
        return f"{self.path} {self.value} {self.timestamp}"

    def submit(self, graphite_address: str | tuple[str, int]):
        GraphiteEvent.submit_many([self], graphite_address)

    @staticmethod
    def submit_many(
        events: list['GraphiteEvent'], graphite_address: str | tuple[str, int]
    ):
        if isinstance(graphite_address, str):
            graphite_host, graphite_port = cast(
                tuple[str, str], tuple(graphite_address.split(':', 1))
            )
            graphite_address_tuple = (graphite_host, int(graphite_port))
        else:
            graphite_address_tuple = graphite_address

        payload = pickle.dumps([event.serialize() for event in events], protocol=2)
        header = struct.pack('!L', len(payload))
        message = header + payload

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect(graphite_address_tuple)
            sock.sendall(message)


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
