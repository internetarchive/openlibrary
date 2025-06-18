import fnmatch
import functools
import os
import subprocess
import typing

from apscheduler.events import (
    EVENT_JOB_ERROR,
    EVENT_JOB_EXECUTED,
    EVENT_JOB_SUBMITTED,
    JobEvent,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.util import undefined


class OlAsyncIOScheduler(AsyncIOScheduler):
    def __init__(self, print_prefix: str):
        super().__init__({'apscheduler.timezone': 'UTC'})
        self.print_prefix = print_prefix
        self.add_listener(
            functools.partial(job_listener, self.print_prefix),
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_SUBMITTED,
        )

    @typing.override
    def add_job(
        self,
        func,
        trigger=None,
        args=None,
        kwargs=None,
        id=None,
        name=None,
        misfire_grace_time=undefined,
        coalesce=undefined,
        max_instances=undefined,
        next_run_time=undefined,
        jobstore="default",
        executor="default",
        replace_existing=False,
        **trigger_args,
    ):
        return super().add_job(
            func,
            trigger,
            args,
            kwargs,
            # Override to avoid duplicating the function name everywhere
            id or func.__name__,
            name,
            misfire_grace_time,
            coalesce,
            max_instances,
            next_run_time,
            jobstore,
            executor,
            replace_existing,
            **trigger_args,
        )

    @typing.override
    def start(self, paused=False):
        """
        Start the configured executors and job stores and begin processing scheduled jobs.

        :param bool paused: if ``True``, don't start job processing until :meth:`resume` is called
        :raises SchedulerAlreadyRunningError: if the scheduler is already running
        :raises RuntimeError: if running under uWSGI with threads disabled

        """
        # Print out all jobs
        jobs = self.get_jobs()
        print(f"[{self.print_prefix}] {len(jobs)} job(s) registered:", flush=True)
        for job in jobs:
            print(f"[{self.print_prefix}]", job, flush=True)

        super().start(paused)
        print(f"[{self.print_prefix}] Scheduler started.", flush=True)


def job_listener(prefix: str, event: JobEvent):
    if event.code == EVENT_JOB_SUBMITTED:
        print(f"[{prefix}] Job {event.job_id} has started.", flush=True)
    elif event.code == EVENT_JOB_EXECUTED:
        print(f"[{prefix}] Job {event.job_id} completed successfully.", flush=True)
    elif event.code == EVENT_JOB_ERROR:
        print(f"[{prefix}] Job {event.job_id} failed.", flush=True)


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
