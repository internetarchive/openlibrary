import asyncio
import json
import re
import time

from scripts.monitoring.utils import GraphiteEvent

IOSTAT_COMMAND = ("iostat", "-x", "-o", "JSON", "5", "2")


def _normalize_metric_name(name: str) -> str:
    normalized = name.replace("/", "_").replace("-", "_")
    normalized = re.sub(r"[^A-Za-z0-9_]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized)
    return normalized.strip("_")


async def get_iostat_payload() -> dict:
    """
    Example:
    {"sysstat": {
        "hosts": [
            {
                "nodename": "blah.foo.org",
                "sysname": "Linux",
                "release": "5.X.X",
                "machine": "x86_64",
                "number-of-cpus": 8,
                "date": "04/23/26",
                "statistics": [
                    {
                        "avg-cpu":  {
                            "user": 58.80,
                            "nice": 0.00,
                            "system": 7.92, "iowait": 5.48, "steal": 7.11, "idle": 20.69},
                            "iowait": 5.48,
                            "steal": 7.11,
                            "idle": 20.69
                        },
                        "disk": [
                            {
                                "disk_device": "vda",
                                "r/s": 2395.37,
                                "w/s": 17.57,
                                "d/s": 0.02,
                                "rkB/s": 72429.16,
                                "wkB/s": 1330.89,
                                "dkB/s": 131.55,
                                "rrqm/s": 1.19,
                                "wrqm/s": 1.84,
                                "drqm/s": 0.00,
                                "rrqm": 0.05,
                                "wrqm": 9.48,
                                "drqm": 0.00,
                                "r_await": 0.72,
                                "w_await": 6.26,
                                "d_await": 0.26,
                                "rareq-sz": 30.24,
                                "wareq-sz": 75.75,
                                "dareq-sz": 7640.70,
                                "aqu-sz": 1.64,
                                "util": 83.79
                            }
                        ]
                    }
                ]
            }
        ]
    }}
    """
    process = await asyncio.create_subprocess_exec(
        *IOSTAT_COMMAND,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"iostat failed with code {process.returncode}: {stderr.decode('utf-8', errors='replace').strip()}")
    return json.loads(stdout.decode("utf-8"))


async def get_iostat_events(bucket: str, timestamp: int | None = None) -> list[GraphiteEvent]:
    payload = await get_iostat_payload()

    hosts = payload.get("sysstat", {}).get("hosts", [])
    if not hosts:
        return []

    latest_statistics = hosts[0].get("statistics", [])
    if not latest_statistics:
        return []

    if timestamp is None:
        timestamp = int(time.time())

    events: list[GraphiteEvent] = []
    stats = latest_statistics[-1]

    avg_cpu = stats.get("avg-cpu", {})
    for metric_name, metric_value in avg_cpu.items():
        if not isinstance(metric_value, (int, float)):
            continue
        events.append(
            GraphiteEvent(
                path=f"{bucket}.iostat.avg_cpu.{_normalize_metric_name(metric_name)}",
                value=float(metric_value),
                timestamp=timestamp,
            )
        )

    for disk_stats in stats.get("disk", []):
        disk_device = _normalize_metric_name(str(disk_stats.get("disk_device", "unknown")))
        for metric_name, metric_value in disk_stats.items():
            if metric_name == "disk_device" or not isinstance(metric_value, (int, float)):
                continue
            events.append(
                GraphiteEvent(
                    path=f"{bucket}.iostat.disk.{disk_device}.{_normalize_metric_name(metric_name)}",
                    value=float(metric_value),
                    timestamp=timestamp,
                )
            )

    return events
