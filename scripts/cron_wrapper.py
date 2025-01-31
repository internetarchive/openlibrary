#!/usr/bin/env python3
"""
Executes the given script with the given arguments, adding profiling and error reporting.
"""

import argparse
import subprocess
import sys
from configparser import ConfigParser
from pathlib import Path

import sentry_sdk
from statsd import StatsClient

DEFAULT_CONFIG_PATH = "/olsystem/etc/cron-wrapper.ini"


class MonitoredJob:
    def __init__(self, command, sentry_cfg, statsd_cfg):
        self.command = command
        self.statsd_client = (
            self._setup_statsd(statsd_cfg.get("host", ""), statsd_cfg.get("port", ""))
            if statsd_cfg
            else None
        )
        self._setup_sentry(sentry_cfg.get("dns", ""))
        self.job_name = self._get_job_name()
        self.job_failed = False

    def run(self):
        self._before_run()
        try:
            self._run_script()
        except subprocess.CalledProcessError as e:
            sentry_sdk.capture_exception(e)
            self.job_failed = True
        finally:
            self._after_run()

    def _before_run(self):
        if self.statsd_client:
            self.statsd_client.incr(f'cron.{self.job_name}.start')
            self.job_timer = self.statsd_client.timer(f'cron.{self.job_name}.duration')
            self.job_timer.start()

    def _after_run(self):
        if self.statsd_client:
            self.job_timer.stop()
            status = "failure" if self.job_failed else "stop"
            self.statsd_client.incr(f'cron.{self.job_name}.{status}')

    def _run_script(self):
        return subprocess.run(
            self.command, text=True, stdout=sys.stdout, stderr=sys.stderr, check=True
        )

    def _setup_sentry(self, dns):
        sentry_sdk.init(dns=dns, trace_sample_rate=1.0)  # Configure?

    def _setup_statsd(self, host, port):
        return StatsClient(host, port)

    def _get_job_name(self):
        script_path = next(
            s for s in self.command if s.startswith("/openlibrary/scripts/")
        )
        script_name = script_path.split('/')[-1]
        job_name = script_name.split('.')[0]
        return job_name


def main(args):
    config = _read_config(args.config)
    sentry_cfg = dict(config["sentry"]) if config.has_section("sentry") else None
    statsd_cfg = dict(config["statsd"]) if config.has_section("statsd") else None
    command = [args.script] + args.script_args

    job = MonitoredJob(command, sentry_cfg, statsd_cfg)
    job.run()


def _read_config(config_path):
    if not Path(config_path).exists():
        raise FileNotFoundError("Missing cron-wrapper configuration file")
    config_parser = ConfigParser()
    config_parser.read(config_path)
    return config_parser


def _parse_args():
    _parser = argparse.ArgumentParser(description=__doc__)
    _parser.add_argument(
        "-c",
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to cron-wrapper configuration file. Defaults to \"{DEFAULT_CONFIG_PATH}\"",
    )
    _parser.add_argument(
        "script", help="Path to script that will be wrapped and monitored"
    )
    _parser.add_argument(
        "script_args",
        nargs=argparse.REMAINDER,
        help="Arguments for the wrapped script",
    )
    _parser.set_defaults(func=main)

    return _parser


if __name__ == '__main__':
    parser = _parse_args()
    args = parser.parse_args()
    args.func(args)
