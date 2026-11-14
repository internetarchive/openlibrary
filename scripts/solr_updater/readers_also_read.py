"""Rebuild the "Readers also read" table (#13825).

trending_updater.py runs this nightly. Run it by hand to rebuild now, or with
--dry-run to print the coverage numbers without writing anything:

    python scripts/solr_updater/readers_also_read.py conf/openlibrary.yml --dry-run
"""

from openlibrary.config import load_config
from openlibrary.core import async_db
from openlibrary.core.readers_also_read import ReadersAlsoRead, RebuildConfig, RebuildSummary
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

_DEFAULTS = RebuildConfig()


async def run_readers_also_read_update(config: RebuildConfig | None = None, dry_run: bool = False) -> RebuildSummary | None:
    summary = await ReadersAlsoRead.rebuild(config, dry_run=dry_run)
    if summary is None:
        print("Readers also read: another rebuild is running, so this one was skipped.", flush=True)
        return None
    print(
        f"Readers also read: {summary.eligible_works} works eligible, {summary.works_with_related} with related works,"
        f" {summary.works_with_carousel} with enough to show a carousel, {summary.rows} rows{' (dry run, nothing written)' if dry_run else ''}.",
        flush=True,
    )
    return summary


async def main(
    ol_config: str,
    min_weighted_entries: float = _DEFAULTS.min_weighted_entries,
    max_books_per_reader: int = _DEFAULTS.max_books_per_reader,
    want_to_read_weight: float = _DEFAULTS.want_to_read_weight,
    include_private_reading_logs: bool = _DEFAULTS.include_private_reading_logs,
    dry_run: bool = False,
) -> None:
    """
    Rebuild the "Readers also read" table now.

    :param ol_config: Path to openlibrary.yml
    :param min_weighted_entries: Score only works with at least this many weighted reading log entries
    :param max_books_per_reader: Leave out readers who have logged more books than this
    :param want_to_read_weight: How much a Want to Read entry counts next to Already Read (1.0)
    :param include_private_reading_logs: Also count readers whose reading log is private
    :param dry_run: Print the coverage numbers, then roll back instead of writing
    """
    load_config(ol_config)
    config = RebuildConfig(
        min_weighted_entries=min_weighted_entries,
        max_books_per_reader=max_books_per_reader,
        want_to_read_weight=want_to_read_weight,
        include_private_reading_logs=include_private_reading_logs,
    )
    try:
        await run_readers_also_read_update(config, dry_run=dry_run)
    finally:
        await async_db.close_pool()


if __name__ == "__main__":
    FnToCLI(main).run()
