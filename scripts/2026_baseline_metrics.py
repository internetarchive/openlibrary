#!/usr/bin/env python
"""
2026 Baseline Metrics Collection Script
Tracks retention and participation metrics for Open Library

Usage:
    python scripts/2026_baseline_metrics.py
    
This script should be run daily via cron.
"""

import sys
import logging
from datetime import datetime, timedelta
from collections import defaultdict

# Add parent directory to path for imports
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import web

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BaselineMetrics:
    """Collects 2026 baseline metrics for Open Library"""
    
    def __init__(self):
        """Initialize metrics collector"""
        self.today = datetime.now().date()
        self.stats = defaultdict(int)
        logger.info(f"Initializing metrics collection for {self.today}")
    
    def collect_retention_metrics(self):
        """
        Collect retention metrics:
        - Daily patron logins
        - Returning logins (users who didn't register this month)
        """
        logger.info("Collecting retention metrics...")
        
        # Count unique logins today
        daily_logins = self._count_daily_logins()
        self.stats['retention.daily_logins'] = daily_logins
        logger.info(f"Daily logins: {daily_logins}")
        
        # Count returning users
        returning_users = self._count_returning_users()
        self.stats['retention.returning_logins'] = returning_users
        logger.info(f"Returning users: {returning_users}")
    
    def collect_participation_metrics(self):
        """
        Collect participation metrics:
        - Unique editors
        - Total edits
        - Edit breakdown by type
        """
        logger.info("Collecting participation metrics...")
        
        # Count unique editors (excluding registrations)
        unique_editors = self._count_unique_editors()
        self.stats['participation.unique_editors'] = unique_editors
        logger.info(f"Unique editors: {unique_editors}")
        
        # Count total edits (excluding registrations)
        total_edits = self._count_total_edits()
        self.stats['participation.total_edits'] = total_edits
        logger.info(f"Total edits: {total_edits}")
        
        # Get edit breakdown by type
        edit_breakdown = self._get_edit_breakdown()
        for edit_type, count in edit_breakdown.items():
            metric_name = f'participation.edits.{edit_type}'
            self.stats[metric_name] = count
            logger.info(f"Edits for {edit_type}: {count}")
    
    def _count_daily_logins(self):
        """Count unique users who logged in today"""
        try:
            # Query to count unique accounts that accessed the system today
            query = """
                SELECT COUNT(DISTINCT account_id) as count
                FROM account_login
                WHERE DATE(created) = $date
            """
            result = web.ctx.site.store.query(query, vars={'date': self.today})
            result_list = list(result)
            return result_list[0].count if result_list else 0
        except Exception as e:
            logger.error(f"Error counting daily logins: {e}")
            return 0
    
    def _count_returning_users(self):
        """
        Count users who logged in today but didn't register this month
        """
        try:
            current_month_start = self.today.replace(day=1)
            
            query = """
                SELECT COUNT(DISTINCT l.account_id) as count
                FROM account_login l
                WHERE DATE(l.created) = $today
                AND l.account_id NOT IN (
                    SELECT id FROM account
                    WHERE DATE(created) >= $month_start
                )
            """
            result = web.ctx.site.store.query(
                query, 
                vars={'today': self.today, 'month_start': current_month_start}
            )
            result_list = list(result)
            return result_list[0].count if result_list else 0
        except Exception as e:
            logger.error(f"Error counting returning users: {e}")
            return 0
    
    def _count_unique_editors(self):
        """
        Count unique users who made edits today
        IMPORTANT: Excludes registration events
        """
        try:
            query = """
                SELECT COUNT(DISTINCT author_id) as count
                FROM transaction
                WHERE DATE(created) = $date
                AND action NOT IN ('register', 'register-account')
            """
            result = web.ctx.site.store.query(query, vars={'date': self.today})
            result_list = list(result)
            return result_list[0].count if result_list else 0
        except Exception as e:
            logger.error(f"Error counting unique editors: {e}")
            return 0
    
    def _count_total_edits(self):
        """
        Count total edits made today
        IMPORTANT: Excludes registration events (fixing bug mentioned in issue)
        """
        try:
            query = """
                SELECT COUNT(*) as count
                FROM transaction
                WHERE DATE(created) = $date
                AND action NOT IN ('register', 'register-account')
            """
            result = web.ctx.site.store.query(query, vars={'date': self.today})
            result_list = list(result)
            return result_list[0].count if result_list else 0
        except Exception as e:
            logger.error(f"Error counting total edits: {e}")
            return 0
    
    def _get_edit_breakdown(self):
        """
        Get breakdown of edits by type:
        - works
        - editions  
        - authors
        - covers
        - tags
        - isbns
        - other
        """
        breakdown = {
            'works': 0,
            'editions': 0,
            'authors': 0,
            'covers': 0,
            'tags': 0,
            'isbns': 0,
            'other': 0
        }
        
        try:
            # Count edits by thing type
            query = """
                SELECT 
                    CASE 
                        WHEN t.key LIKE '/works/%' THEN 'works'
                        WHEN t.key LIKE '/books/%' THEN 'editions'
                        WHEN t.key LIKE '/authors/%' THEN 'authors'
                        WHEN t.key LIKE '/b/%' THEN 'covers'
                        ELSE 'other'
                    END as edit_type,
                    COUNT(*) as count
                FROM transaction tr
                JOIN thing t ON tr.thing_id = t.id
                WHERE DATE(tr.created) = $date
                AND tr.action NOT IN ('register', 'register-account')
                GROUP BY edit_type
            """
            results = web.ctx.site.store.query(query, vars={'date': self.today})
            
            for row in results:
                if row.edit_type in breakdown:
                    breakdown[row.edit_type] = row.count
            
            # Count tag and ISBN edits separately
            breakdown['tags'] = self._count_tag_edits()
            breakdown['isbns'] = self._count_isbn_edits()
            
        except Exception as e:
            logger.error(f"Error getting edit breakdown: {e}")
        
        return breakdown
    
    def _count_tag_edits(self):
        """Count edits related to tags/subjects"""
        try:
            query = """
                SELECT COUNT(*) as count
                FROM transaction tr
                JOIN version v ON tr.id = v.transaction_id
                WHERE DATE(tr.created) = $date
                AND tr.action NOT IN ('register', 'register-account')
                AND v.revision LIKE '%subject%'
            """
            result = web.ctx.site.store.query(query, vars={'date': self.today})
            result_list = list(result)
            return result_list[0].count if result_list else 0
        except Exception as e:
            logger.error(f"Error counting tag edits: {e}")
            return 0
    
    def _count_isbn_edits(self):
        """Count edits related to ISBNs"""
        try:
            query = """
                SELECT COUNT(*) as count
                FROM transaction tr
                JOIN version v ON tr.id = v.transaction_id
                WHERE DATE(tr.created) = $date
                AND tr.action NOT IN ('register', 'register-account')
                AND (v.revision LIKE '%isbn%' OR v.revision LIKE '%ISBN%')
            """
            result = web.ctx.site.store.query(query, vars={'date': self.today})
            result_list = list(result)
            return result_list[0].count if result_list else 0
        except Exception as e:
            logger.error(f"Error counting ISBN edits: {e}")
            return 0
    
    def send_to_statsd(self):
        """Send collected metrics to StatsD"""
        try:
            # Try to import statsd if available
            try:
                import statsd
                stats_client = statsd.StatsClient('localhost', 8125, prefix='openlibrary')
                
                for metric_name, value in self.stats.items():
                    stats_client.gauge(metric_name, value)
                    logger.info(f"Sent to StatsD: {metric_name} = {value}")
                
                logger.info("Successfully sent all metrics to StatsD")
                return True
            except ImportError:
                logger.warning("StatsD client not available, metrics not sent to StatsD")
                return False
        except Exception as e:
            logger.error(f"Error sending metrics to StatsD: {e}")
            return False
    
    def print_summary(self):
        """Print a summary of collected metrics"""
        print("\n" + "="*60)
        print(f"  2026 BASELINE METRICS SUMMARY - {self.today}")
        print("="*60)
        
        print("\n📊 RETENTION METRICS:")
        print(f"  Daily Logins: {self.stats.get('retention.daily_logins', 0)}")
        print(f"  Returning Users: {self.stats.get('retention.returning_logins', 0)}")
        
        print("\n✏️  PARTICIPATION METRICS:")
        print(f"  Unique Editors: {self.stats.get('participation.unique_editors', 0)}")
        print(f"  Total Edits: {self.stats.get('participation.total_edits', 0)}")
        
        print("\n📚 EDIT BREAKDOWN:")
        print(f"  Works: {self.stats.get('participation.edits.works', 0)}")
        print(f"  Editions: {self.stats.get('participation.edits.editions', 0)}")
        print(f"  Authors: {self.stats.get('participation.edits.authors', 0)}")
        print(f"  Covers: {self.stats.get('participation.edits.covers', 0)}")
        print(f"  Tags: {self.stats.get('participation.edits.tags', 0)}")
        print(f"  ISBNs: {self.stats.get('participation.edits.isbns', 0)}")
        print(f"  Other: {self.stats.get('participation.edits.other', 0)}")
        
        print("\n" + "="*60 + "\n")
    
    def run(self):
        """Main execution method"""
        try:
            logger.info("Starting 2026 baseline metrics collection")
            
            # Collect all metrics
            self.collect_retention_metrics()
            self.collect_participation_metrics()
            
            # Send to StatsD
            self.send_to_statsd()
            
            # Print summary
            self.print_summary()
            
            logger.info("Metrics collection completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error during metrics collection: {e}", exc_info=True)
            return False


def main():
    """Main entry point"""
    # Load Open Library config
    try:
        import infogami
        from infogami import config
        from openlibrary.config import load_config
        
        # Try to load config
        load_config('/olsystem/etc/openlibrary.yml')
    except Exception as e:
        logger.warning(f"Could not load full config: {e}")
        logger.info("Continuing with basic setup...")
    
    # Create and run metrics collector
    collector = BaselineMetrics()
    success = collector.run()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()