import datetime
import itertools
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Generator, Iterable
from dataclasses import dataclass

from scripts.monitoring.haproxy_monitor import GraphiteEvent
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI


@dataclass
class SolrLogEntry:
    timestamp: str
    log_level: str
    thread_info: str
    context: str
    class_handler: str
    message: str


# Sample logs:
# 2025-01-14 20:50:33.796 INFO  (qtp1997548433-42-null-243439) [c: s: r: x:openlibrary t:null-243439] o.a.s.c.S.Request webapp=/solr path=/select params={q=({!edismax+q.op%3D"AND"+qf%3D"text+alternative_title^10+author_name^10"+pf%3D"alternative_title^10+author_name^10"+bf%3D"min(100,edition_count)+min(100,def(readinglog_count,0))"+v%3D$workQuery})&spellcheck=true&fl=*&start=0&fq=type:work&fq=ebook_access:[borrowable+TO+*]&spellcheck.count=3&sort=first_publish_year+desc&rows=12&workQuery=ebook_access:[borrowable+TO+*]+-key:"\/works\/OL4420181W"+author_key:(OL874808A)&wt=json} hits=2 status=0 QTime=12  # noqa: E501
@dataclass
class RequestLogEntry(SolrLogEntry):
    timestamp: str
    log_level: str
    thread_info: str
    context: str
    class_handler: str
    webapp: str
    path: str
    params: str
    status: int
    qtime: int
    other_fields: dict

    @staticmethod
    def parse_log_entry(match: re.Match) -> 'RequestLogEntry':
        fields = {
            kvp.split('=', 1)[0]: kvp.split('=', 1)[1]
            for kvp in match.group('message').split(' ')
        }
        return RequestLogEntry(
            timestamp=match.group('timestamp'),
            log_level=match.group('log_level'),
            thread_info=match.group('thread_info'),
            context=match.group('context'),
            class_handler=match.group('class_handler'),
            message=match.group('message'),
            webapp=fields['webapp'],
            path=fields['path'],
            params=fields['params'],
            status=int(fields['status']),
            qtime=int(fields['QTime']),
            other_fields={
                k: v
                for k, v in fields.items()
                if k not in {'webapp', 'path', 'params', 'status', 'QTime'}
            },
        )


def parse_log_entry(log_line: str) -> 'SolrLogEntry':
    log_pattern = re.compile(
        r'^(?P<timestamp>\S+ \S+) (?P<log_level>\S+) +\((?P<thread_info>.*?)\) \[(?P<context>.*?)\] (?P<class_handler>\S+) (?P<message>.*)$'
    )

    match = log_pattern.match(log_line)
    if not match:
        raise ValueError(f"Failed to parse log line: {log_line}")

    if match.group('class_handler') == 'o.a.s.c.S.Request':
        return RequestLogEntry.parse_log_entry(match)
    else:
        return SolrLogEntry(
            timestamp=match.group('timestamp'),
            log_level=match.group('log_level'),
            thread_info=match.group('thread_info'),
            context=match.group('context'),
            class_handler=match.group('class_handler'),
            message=match.group('message'),
        )


def groupby_buffered[T, U](
    iterable: Iterable[T],
    key_func: Callable[[T], U],
    buffer: int = 0,
) -> Generator[list[T], None, None]:
    current_group: list[T] = []
    current_key: U | None = None
    buffered: list[T] = []
    queue = iterable

    for item in queue:
        key = key_func(item)
        if not current_group:
            # Initial case
            current_key = key
            # print('N', key)
            current_group.append(item)
        elif key == current_key:
            # print('+', key)
            current_group.append(item)
        else:
            # print('B', key)
            buffered.append(item)
            # Different, add to buffer
            if len(buffered) > buffer:
                # Run out of buffer, time to move on
                yield current_group
                current_group = []
                current_key = None
                # Note we don't need to make this recursive because there will always be <buffer length
                # items in the buffered array
                queue = itertools.chain(buffered, iterable)
    if current_group:
        yield current_group
    if buffered:
        for key, grp in itertools.groupby(buffered, key_func):
            yield list(grp)


def stream_docker_logs(container_name: str) -> Generator[str, None, None]:
    process = subprocess.Popen(
        ['docker', 'logs', '--tail=0', '-f', container_name],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout
    assert process.stderr
    try:
        for line in iter(process.stdout.readline, b''):
            yield line.decode('utf-8').strip()
    except KeyboardInterrupt:
        process.terminate()
    finally:
        process.stdout.close()
        process.stderr.close()


def safe_parse_log_entry(log_line: str) -> RequestLogEntry | SolrLogEntry | None:
    try:
        return parse_log_entry(log_line)
    except Exception as e:  # noqa: BLE001
        print(f"Error parsing log line: {log_line}\n{e}")
        return None


def standard_duration_blocks(ms: int) -> str:
    blocks = (
        10,
        100,
        1000,
        5000,
        10000,
        20000,
    )
    for block in blocks:
        if ms <= block:
            return f"{block}ms"
    return "LONG"


def graphite_normalize(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_-]', '_', name)


def main(
    solr_container='openlibrary-solr-1',
    graphite_prefix='stats.ol.solr0',
    graphite_address='graphite.us.archive.org:2004',
):
    # signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    try:
        for minute_log_lines in groupby_buffered(
            (
                entry
                for line in stream_docker_logs(solr_container)
                if (entry := safe_parse_log_entry(line)) is not None
            ),
            key_func=lambda x: x.timestamp[:16],  # Group by minute
            buffer=5,  # TMP
            # buffer=25,  # Keep lines of logs in memory
        ):
            # eg '2025-01-14 20:50:33.796'
            timestamp_str = minute_log_lines[0].timestamp
            # parse the string and convert to an int
            timestamp_int = int(
                datetime.datetime.strptime(
                    timestamp_str, '%Y-%m-%d %H:%M:%S.%f'
                ).timestamp()
            )

            events: list[GraphiteEvent] = []

            total_count = sum(
                1 for entry in minute_log_lines if isinstance(entry, RequestLogEntry)
            )
            events.append(
                GraphiteEvent(
                    path=f"{graphite_prefix}.requests.total",
                    value=total_count,
                    timestamp=timestamp_int,
                )
            )
            count_by_path = Counter(
                graphite_normalize(entry.path.lstrip('/'))
                for entry in minute_log_lines
                if isinstance(entry, RequestLogEntry)
            )
            for path, count in count_by_path.items():
                events.append(
                    GraphiteEvent(
                        path=f"{graphite_prefix}.requests.path.{path}",
                        value=count,
                        timestamp=timestamp_int,
                    )
                )
            count_by_time = Counter(
                standard_duration_blocks(entry.qtime)
                for entry in minute_log_lines
                if isinstance(entry, RequestLogEntry)
            )
            for duration, count in count_by_time.items():
                events.append(
                    GraphiteEvent(
                        path=f"{graphite_prefix}.requests.time.{duration}",
                        value=count,
                        timestamp=timestamp_int,
                    )
                )

            for event in events:
                print(event.serialize())

            GraphiteEvent.submit_many(events, graphite_address)
    except BrokenPipeError:
        sys.exit(0)


if __name__ == "__main__":
    FnToCLI(main).run()
