"""
Retry worker for failed Solr updates (Issue #10737).

Continuously polls solr_update_failures table and retries with exponential backoff.
"""

import asyncio
import logging

from openlibrary.config import load_config
from openlibrary.core import db
from openlibrary.solr import update
from openlibrary.utils.shutdown import setup_graceful_shutdown

logger = logging.getLogger("openlibrary.solr-retry-worker")
setup_graceful_shutdown()


def get_ready_failures(limit=100):
    """Get failures ready to retry."""
    try:
        results = db.query(
            """
            SELECT id, keys, entity_type, retry_count, error_type, max_retries
            FROM solr_update_failures
            WHERE next_retry_at <= NOW()
            AND retry_count < max_retries
            ORDER BY first_failed_at ASC
            LIMIT $1
            """,
            limit,
        )
        return list(results)
    except Exception as e:
        logger.error(f"Failed to query ready failures: {e}", exc_info=True)
        return []


def archive_failure(failure_id):
    """Archive a failure that exceeded max retries."""
    try:
        db.query(
            """
            INSERT INTO solr_update_failures_archived
            SELECT *, NOW() as archived_at, 'max_retries_exceeded' as archived_reason,
                   NULL as manual_resolution_notes, NULL as resolved_at, NULL as resolved_by
            FROM solr_update_failures
            WHERE id = $1
            """,
            failure_id,
        )

        db.query("DELETE FROM solr_update_failures WHERE id = $1", failure_id)

        logger.critical(
            f"Archived failure {failure_id} after exceeding max retries",
            extra={'failure_id': failure_id},
        )
    except Exception as e:
        logger.error(f"Failed to archive failure {failure_id}: {e}", exc_info=True)


async def retry_failure(failure):
    """Retry a single failed batch."""
    failure_id = failure['id']
    keys = failure['keys']
    entity_type = failure['entity_type']
    retry_count = failure['retry_count']
    max_retries = failure['max_retries']

    logger.info(
        f"Retrying batch {failure_id}: {len(keys)} {entity_type} keys "
        f"(attempt {retry_count + 1}/{max_retries})",
        extra={
            'failure_id': failure_id,
            'keys_sample': keys[:5],
            'total_keys': len(keys),
            'entity_type': entity_type,
            'retry_count': retry_count,
        },
    )

    try:
        await update.update_keys(keys, commit=True)

        db.query("DELETE FROM solr_update_failures WHERE id = $1", failure_id)

        logger.info(
            f"Successfully retried batch {failure_id} ({len(keys)} keys)",
            extra={
                'failure_id': failure_id,
                'retry_count': retry_count,
                'keys_count': len(keys),
            },
        )
        return True

    except Exception as e:
        logger.error(
            f"Retry failed for batch {failure_id}: {e}",
            extra={
                'failure_id': failure_id,
                'retry_count': retry_count,
                'error_type': type(e).__name__,
            },
            exc_info=True,
        )

        new_retry_count = retry_count + 1
        if new_retry_count >= max_retries:
            archive_failure(failure_id)
        else:
            logger.warning(
                f"Batch {failure_id} failed retry {new_retry_count}/{max_retries}"
            )

        return False


def get_queue_stats():
    """Get statistics about the failure queue for monitoring."""
    try:
        results = db.query(
            """
            SELECT
                COUNT(*) as total_failures,
                COUNT(*) FILTER (WHERE retry_count = 0) as first_attempt_failures,
                COUNT(*) FILTER (WHERE retry_count >= 5) as high_retry_count,
                EXTRACT(EPOCH FROM (NOW() - MIN(first_failed_at))) as oldest_failure_age_seconds,
                COUNT(*) FILTER (WHERE next_retry_at <= NOW()) as ready_to_retry,
                SUM(array_length(keys, 1)) as total_keys_affected
            FROM solr_update_failures
            """
        )
        return list(results)[0] if results else None
    except Exception as e:
        logger.error(f"Failed to get queue stats: {e}", exc_info=True)
        return None


async def main(
    ol_config: str,
    ol_url: str = 'http://openlibrary.org/',
    poll_interval: int = 30,
    batch_size: int = 100,
):
    """Main retry worker loop."""
    logger.info("Starting Solr retry worker")
    logger.info(f"Config: {ol_config}, URL: {ol_url}")
    logger.info(f"Poll interval: {poll_interval}s, Batch size: {batch_size}")

    load_config(ol_config)
    update.load_configs(ol_url, ol_config, 'default')

    iteration = 0

    while True:
        iteration += 1
        try:
            failures = get_ready_failures(limit=batch_size)

            if failures:
                logger.info(
                    f"Iteration {iteration}: Found {len(failures)} failures ready to retry"
                )

                success_count = 0
                for failure in failures:
                    if await retry_failure(failure):
                        success_count += 1

                    await asyncio.sleep(0.5)

                logger.info(
                    f"Iteration {iteration} complete: {success_count}/{len(failures)} succeeded"
                )
            else:
                logger.debug(f"Iteration {iteration}: No failures ready to retry")

            if iteration % 10 == 0:
                stats = get_queue_stats()
                if stats:
                    logger.info(
                        f"Queue stats: {stats['total_failures']} total failures, "
                        f"{stats['ready_to_retry']} ready to retry, "
                        f"{stats['total_keys_affected']} keys affected",
                        extra=dict(stats),
                    )

        except Exception:
            logger.error(
                f"Error in retry worker loop (iteration {iteration})", exc_info=True
            )

        await asyncio.sleep(poll_interval)


if __name__ == "__main__":
    from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

    cli = FnToCLI(main)
    cli.run()
