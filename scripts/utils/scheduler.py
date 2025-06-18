import functools
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
