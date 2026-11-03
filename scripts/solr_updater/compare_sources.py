"""Check that both Solr updater sources find the same keys for the same edits. Read-only.

Reads the Infobase write log from ``--since`` and, for every save in it, the same
transaction from the ``transaction`` table, and compares the keys each source
would reindex. It also lists transactions the database has but the log doesn't
(for example writes the log never recorded) and admin force-update requests.
Nothing is written anywhere, so it is safe to run against production.

Run it where the solr-updater runs (it needs the database and the Infobase log):

    docker compose exec solr-updater python scripts/solr_updater/compare_sources.py \\
        /olsystem/etc/openlibrary.yml 2026-11-03T00:00

Exits 1 if any transaction's keys differ.
"""

import datetime as dt
import json
import sys

from infogami import config
from openlibrary.config import load_config
from scripts.solr_updater.solr_updater import InfobaseLog, InfobaseLogRecord, parse_log
from scripts.solr_updater.transaction_log import TransactionLog, force_update_requests


def read_log(since: dt.datetime, until: dt.datetime) -> list[InfobaseLogRecord]:
    """Infobase log records with a timestamp in [since, until)."""
    log = InfobaseLog(config.get("infobase_server"))
    log.seek(f"{since.date().isoformat()}:0")
    records: list[InfobaseLogRecord] = []
    while True:
        offset = log.tell()
        for record in log.read_records():
            if since <= dt.datetime.fromisoformat(record["timestamp"]) < until:
                records.append(record)
        if log.tell() == offset:
            return records


def transaction_id(record: InfobaseLogRecord) -> int | None:
    if record.get("action") in ("save", "save_many") and (changeset := record["data"].get("changeset")):
        return int(changeset["id"])
    return None


async def read_transactions(first: int, last: int) -> dict[int, list[str]]:
    log = TransactionLog(first - 1, batch_size=1000, until=last)
    keys: dict[int, list[str]] = {}
    while (batch := await log.read()).transaction_count:
        keys.update(batch.keys_by_transaction)
        log.commit()
    return keys


async def main(ol_config: str, since: str, until: str | None = None, show: int = 20) -> int:
    """
    :param since: UTC datetime to start comparing from, e.g. 2026-11-03T00:00
    :param until: UTC datetime to stop at; defaults to 10 minutes ago, so in-flight edits have landed in both
    :param show: How many differing transactions to print in full
    """
    load_config(ol_config)
    start = dt.datetime.fromisoformat(since)
    end = dt.datetime.fromisoformat(until) if until else dt.datetime.now(dt.UTC).replace(tzinfo=None) - dt.timedelta(minutes=10)

    records = read_log(start, end)
    log_keys = {tx_id: list(dict.fromkeys(parse_log([record]))) for record in records if (tx_id := transaction_id(record))}
    log_forced = [key for record in records if record.get("action") == "store.put" for key in parse_log([record])]
    if not log_keys:
        print(json.dumps({"since": str(start), "until": str(end), "log_records": len(records), "error": "no saves in the log for this window"}))
        return 1

    db_keys = await read_transactions(min(log_keys), max(log_keys))
    db_forced = [key for r in await force_update_requests() if start <= dt.datetime.fromisoformat(r["time"]) < end for key in r["keys"]]

    differing = {tx_id: {"log": keys, "db": db_keys.get(tx_id)} for tx_id, keys in log_keys.items() if set(keys) != set(db_keys.get(tx_id) or [])}
    only_db = {tx_id: keys for tx_id, keys in db_keys.items() if tx_id not in log_keys}
    summary = {
        "since": str(start),
        "until": str(end),
        "transactions_in_log": len(log_keys),
        "transactions_in_db": len(db_keys),
        "same_keys": len(log_keys) - len(differing),
        "different_keys": len(differing),
        "only_in_db": len(only_db),
        "force_update_keys": {"log": len(log_forced), "db": len(db_forced), "same": set(log_forced) == set(db_forced)},
        "examples_different": dict(list(differing.items())[:show]),
        "examples_only_in_db": dict(list(only_db.items())[:show]),
    }
    print(json.dumps(summary, indent=1, default=str))
    return 1 if differing else 0


if __name__ == "__main__":
    from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

    sys.exit(FnToCLI(main).run())
