# 2026 Baseline Metrics

## Overview

This document describes the 2026 baseline metrics tracking system implemented for Open Library.

## Metrics Collected

### Retention Metrics

1. **Daily Logins** (`retention.daily_logins`)
   - Number of unique patrons who logged into Open Library each day
   - Tracked via session activity in the store table

2. **Returning Users** (`retention.returning_logins`)
   - Number of users who logged in but did not register in the current month
   - Helps track user engagement vs new user acquisition

### Participation Metrics

1. **Unique Editors** (`participation.unique_editors`)
   - Number of distinct users who made at least one edit
   - Excludes registration events

2. **Total Edits** (`participation.total_edits`)
   - Total number of edits made
   - **Important**: Excludes registration events (fixing previous bug)

3. **Edit Breakdown**
   - `participation.edits.works` - Edits to work records
   - `participation.edits.editions` - Edits to edition/book records
   - `participation.edits.authors` - Edits to author records
   - `participation.edits.covers` - Edits to cover images
   - `participation.edits.tags` - Edits to tags/subjects
   - `participation.edits.isbns` - Edits to ISBN fields
   - `participation.edits.other` - Other types of edits

## Implementation

### Script Location
`scripts/2026_baseline_metrics.py`

### Execution Schedule
Runs daily at 2:00 AM via cron

### Data Storage
Metrics are sent to StatsD for aggregation and visualization

## Bug Fixes

### Registration Counting as Edits
**Problem**: Previously, user registrations were incorrectly counted as edits in the total edit count.

**Solution**: The `_count_total_edits()` and `_count_unique_editors()` methods now explicitly exclude transactions with `action = 'register'` or `action = 'register-account'`.

## Testing

Run tests with:
```bash
docker compose run --rm home pytest tests/unit/test_2026_baseline_metrics.py -v
```

## Manual Execution

To manually run the metrics collection:
```bash
docker compose exec web bash
cd /openlibrary
PYTHONPATH=. python scripts/2026_baseline_metrics.py
```

## Monitoring

Metrics can be viewed in your StatsD/Graphite dashboard under the `openlibrary` namespace.

## Related Issues

- Issue #11714: 2026 Baseline Metrics