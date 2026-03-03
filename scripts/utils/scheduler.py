import functools
import typing
from typing import TYPE_CHECKING, cast

from apscheduler.events import (
    EVENT_JOB_ERROR,
    EVENT_JOB_EXECUTED,
    EVENT_JOB_SUBMITTED,
    JobEvent,
    JobExecutionEvent,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.util import undefined


class OlAsyncIOScheduler(AsyncIOScheduler):
    def __init__(self, print_prefix: str, sentry_monitoring: bool = False):
        super().__init__({'apscheduler.timezone': 'UTC'})
        self.print_prefix = print_prefix
        self.sentry = sentry_monitoring
        self.add_listener(
            functools.partial(print_job_listener, self.print_prefix),
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
        if TYPE_CHECKING:
            from sentry_sdk._types import MonitorConfig  # noqa: PLC0415

        monitor_config: MonitorConfig = {
            'checkin_margin': 60,
        }

        if self.sentry:
            from sentry_sdk.crons import monitor  # noqa: PLC0415

            monitored_func = monitor(id or func.__name__, monitor_config)(func)
            # Preserve the original function name
            monitored_func.__name__ = func.__name__
            func = monitored_func

        job = super().add_job(
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

        if self.sentry:
            if isinstance(job.trigger, CronTrigger):
                monitor_config['schedule'] = {
                    'type': 'crontab',
                    'value': cron_trigger_to_crontab(job.trigger),
                }
                print(
                    f"[{self.print_prefix}] Monitoring job {job.id} with crontab: {monitor_config['schedule']['value']}",
                    flush=True,
                )
            else:
                raise ValueError(
                    f"Unsupported trigger type: {type(job.trigger).__name__}. "
                    "Only CronTrigger is supported for Sentry monitoring."
                )

        return job

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


def print_job_listener(prefix: str, event: JobEvent):
    if event.code == EVENT_JOB_SUBMITTED:
        print(f"[{prefix}] Job {event.job_id} has started.", flush=True)
    elif event.code == EVENT_JOB_EXECUTED:
        print(f"[{prefix}] Job {event.job_id} completed successfully.", flush=True)
    elif event.code == EVENT_JOB_ERROR:
        event = cast(JobExecutionEvent, event)
        print(f"[{prefix}] Job {event.job_id} failed.", flush=True)
        if event.exception:
            print(event.traceback, flush=True)


def cron_trigger_to_crontab(cron_trigger: CronTrigger) -> str:
    """
    Returns a standard crontab string representation of this trigger.
    Only the fields minute, hour, day, month, and day_of_week are included, as per crontab format.
    """
    # Map field names to crontab order
    crontab_fields = ['minute', 'hour', 'day', 'month', 'day_of_week']
    field_map = {f.name: str(f) for f in cron_trigger.fields}
    return ' '.join(field_map.get(name, '*') for name in crontab_fields)
