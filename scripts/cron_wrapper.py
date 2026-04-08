#!/usr/bin/env python3
"""
Adds Sentry cron monitoring to the given script, then executes the script with the given arguments.
"""

import argparse
import subprocess
import sys
from pathlib import Path

import sentry_sdk
import yaml

DEFAULT_CONFIG_PATH = "/olsystem/etc/openlibrary.yml"


class MonitoredJob:
    def __init__(self, command, sentry_cfg, monitor_slug):
        self.command = command
        self._setup_sentry(sentry_cfg.get("dsn", ""))
        self.monitor_slug = monitor_slug

    def run(self):
        try:
            with sentry_sdk.monitor(self.monitor_slug):
                self._run_script()
        except subprocess.CalledProcessError as e:
            sys.stderr.write(e.stderr)
            sys.stderr.flush()
        finally:
            sentry_sdk.flush()

    def _run_script(self):
        return subprocess.run(
            self.command,
            text=True,
            stdout=sys.stdout,
            stderr=subprocess.PIPE,
            check=True,
        )

    def _setup_sentry(self, dsn):
        sentry_sdk.init(dsn=dsn, traces_sample_rate=1.0)  # Configure?


def main(args):
    config = _read_config(args.config)
    sentry_cfg = config.get("sentry_cron_jobs", {})
    config = None
    command = [args.script] + args.script_args
    monitor_slug = args.monitor_slug

    job = MonitoredJob(command, sentry_cfg, monitor_slug)
    job.run()


def _read_config(config_path):
    if not Path(config_path).exists():
        raise FileNotFoundError("Missing cron-wrapper configuration file")
    with open(config_path) as in_file:
        config = yaml.safe_load(in_file)
        return config


def _parse_args():
    _parser = argparse.ArgumentParser(description=__doc__)
    _parser.add_argument(
        "-c",
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to cron-wrapper configuration file. Defaults to \"{DEFAULT_CONFIG_PATH}\"",
    )
    _parser.add_argument("monitor_slug", help="Monitor slug of the Sentry cron monitor")
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
