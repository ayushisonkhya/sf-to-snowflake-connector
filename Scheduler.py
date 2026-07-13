"""
scheduler.py
============
Runs the Salesforce → Snowflake sync automatically on a schedule.

How to use:
  python scheduler.py          ← runs forever, syncing every N hours
  python scheduler.py --now    ← runs one sync immediately, then starts schedule

Interval is set in config.py:
  SCHEDULE_INTERVAL_HOURS=1

Install dependency:
  pip install apscheduler
"""

import argparse
import logging
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from connector import run
from config import SALESFORCE_OBJECTS, SYNC_MODE, SCHEDULE_INTERVAL_HOURS

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def scheduled_sync():
    """Called automatically by APScheduler on every interval tick."""
    log.info(f"⏰ Scheduled sync triggered at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    run(objects=SALESFORCE_OBJECTS, mode=SYNC_MODE)


def main():
    parser = argparse.ArgumentParser(description="Salesforce → Snowflake Scheduler")
    parser.add_argument(
        "--now",
        action="store_true",
        help="Run one sync immediately before starting the schedule",
    )
    args = parser.parse_args()

    log.info("=" * 60)
    log.info(f"  Scheduler starting — every {SCHEDULE_INTERVAL_HOURS}h  |  mode: {SYNC_MODE}")
    log.info("=" * 60)

    if args.now:
        log.info("  Running immediate sync before schedule starts...")
        scheduled_sync()

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        func     = scheduled_sync,
        trigger  = IntervalTrigger(hours=SCHEDULE_INTERVAL_HOURS),
        id       = "sf_snowflake_sync",
        name     = "Salesforce → Snowflake sync",
        replace_existing = True,
    )

    jobs = scheduler.get_jobs()
    if jobs:
        log.info(f"  Next scheduled run: in {SCHEDULE_INTERVAL_HOURS} hour(s)")
    log.info("  Press Ctrl+C to stop.\n")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        log.info("  Scheduler stopped.")


if __name__ == "__main__":
    main()