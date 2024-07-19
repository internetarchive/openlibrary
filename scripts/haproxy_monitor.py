#!/usr/bin/env python
import asyncio
from dataclasses import dataclass
import math
import pickle
import re
import socket
import struct
import requests
import csv
import time

# Sample graphite events:
# stats.ol.haproxy.ol-web-app-in.FRONTEND.scur
# stats.ol.haproxy.ol-web-app-in.FRONTEND.rate
# stats.ol.haproxy.ol-web-app.BACKEND.qcur
# stats.ol.haproxy.ol-web-app.BACKEND.scur
# stats.ol.haproxy.ol-web-app.BACKEND.rate
# stats.ol.haproxy.ol-web-app-overload.BACKEND.qcur


@dataclass
class GraphiteEvent:
    path: str
    value: float
    timestamp: int

    def serialize(self):
        return (self.path, (self.timestamp, self.value))


@dataclass
class HaproxyCapture:
    # See https://gist.github.com/alq666/20a464665a1086de0c9ddf1754a9b7fb
    pxname: str
    svname: str
    field: list[str]

    def matches(self, row: dict) -> bool:
        return bool(
            re.match(self.pxname, row['pxname'])
            and re.match(self.svname, row['svname'])
            and any(row[field] for field in self.field)
        )

    def to_graphite_events(self, prefix: str, row: dict, ts: float):
        for field in self.field:
            if not row[field]:
                continue
            yield GraphiteEvent(
                path=f'{prefix}.{row["pxname"]}.{row["svname"]}.{field}',
                value=float(row[field]),
                timestamp=math.floor(ts),
            )


TO_CAPTURE = HaproxyCapture(r'.*', r'FRONTEND|BACKEND', ['scur', 'rate', 'qcur'])


def fetch_events(haproxy_url: str, prefix: str, ts: float):
    haproxy_dash_csv = requests.get(f'{haproxy_url};csv').text.lstrip('# ')

    # Parse the CSV; the first row is the header, and then iterate over the rows as dicts

    reader = csv.DictReader(haproxy_dash_csv.splitlines())

    for row in reader:
        if not TO_CAPTURE.matches(row):
            continue
        yield from TO_CAPTURE.to_graphite_events(prefix, row, ts)


async def main(
    haproxy_url='http://openlibrary.org/admin?stats',
    graphite_address='graphite.us.archive.org:2004',
    prefix='stats.ol.haproxy',
    dry_run=True,
    fetch_freq=10,
    commit_freq=30,
):
    graphite_address = tuple(graphite_address.split(':', 1))
    graphite_address = (graphite_address[0], int(graphite_address[1]))

    events_buffer: list[GraphiteEvent] = []
    last_commit_ts: float = 0

    while True:
        ts = time.time()
        events_buffer += fetch_events(haproxy_url, prefix, ts)

        if ts - last_commit_ts > commit_freq:
            for e in events_buffer:
                print(e.serialize())

            if not dry_run:
                payload = pickle.dumps(
                    [e.serialize() for e in events_buffer], protocol=2
                )
                header = struct.pack("!L", len(payload))
                message = header + payload

                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.connect(graphite_address)
                    sock.sendall(message)

            events_buffer = []
            last_commit_ts = ts

        await asyncio.sleep(fetch_freq)


if __name__ == '__main__':
    from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

    FnToCLI(main).run()
