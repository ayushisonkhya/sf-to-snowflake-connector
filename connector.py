"""
connector.py
============
Main entry point. Orchestrates the full sync pipeline.

Modes:
  full        → TRUNCATE table, reload all records
  incremental → MERGE on Id (update existing + insert new)

How to use:
  python connector.py --object Account
  python connector.py --object Account --mode full
  python connector.py --all
  python connector.py --all --mode full
"""

import argparse
import logging
from datetime import datetime

from salesforce_client import SalesforceClient
from snowflake_client import SnowflakeClient
from schema_mapper import map_sf_field_to_snowflake
from alerting import send_failure_alert, send_success_summary
from retry import with_retry
from config import SALESFORCE_OBJECTS, SYNC_MODE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def sync_object(sf_client, sf_object_name, snow_client, mode="incremental"):
    """
    Full pipeline for one Salesforce object.

    full mode:
      1. Describe schema
      2. Map types
      3. Create table if not exists
      4. TRUNCATE table
      5. Query ALL records from Salesforce
      6. INSERT all records (write_pandas)

    incremental mode:
      1. Describe schema
      2. Map types
      3. Create table if not exists
      4. Get last sync time from _SYNC_LOG
      5. Query only NEW/CHANGED records (SystemModstamp >= last sync)
      6. MERGE records into Snowflake (update existing + insert new)
    """
    log.info(f"─── Syncing: {sf_object_name}  [{mode}] ───")
    started_at  = datetime.utcnow()
    rows_loaded = 0

    # ── Step 1: Fetch schema ──────────────────────────────────────────────
    log.info(f"  [1/6] Fetching schema for '{sf_object_name}'...")

    @with_retry
    def describe():
        return sf_client.describe_object(sf_object_name)

    sf_fields = describe()
    log.info(f"        {len(sf_fields)} fields found.")

    # ── Step 2: Map field types ───────────────────────────────────────────
    log.info(f"  [2/6] Mapping field types...")
    snowflake_columns = []
    for field in sf_fields:
        col_name = field["name"].upper()
        col_type = map_sf_field_to_snowflake(field["type"])
        snowflake_columns.append(f'    "{col_name}"  {col_type}')
    snowflake_columns.append('    "_LOADED_AT"  TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP()')

    table_name  = sf_object_name.upper()
    columns_sql = ",\n".join(snowflake_columns)
    create_sql  = f"CREATE TABLE IF NOT EXISTS {table_name} (\n{columns_sql}\n);"

    # ── Step 3: Create table if not exists ───────────────────────────────
    log.info(f"  [3/6] Ensuring table '{table_name}' exists...")
    snow_client.execute(create_sql)

    # ── Step 4: Full → truncate | Incremental → get watermark ────────────
    field_names = [f["name"] for f in sf_fields]
    since       = None

    if mode == "full":
        log.info(f"  [4/6] Full refresh — truncating '{table_name}'...")
        snow_client.execute(f"TRUNCATE TABLE IF EXISTS {table_name}")
    else:
        since = snow_client.get_last_sync_time(sf_object_name)
        if since:
            log.info(f"  [4/6] Incremental — records modified since {since}")
        else:
            log.info(f"  [4/6] Incremental — no prior sync, doing full load")

    # ── Step 5: Query Salesforce ──────────────────────────────────────────
    log.info(f"  [5/6] Querying Salesforce...")

    @with_retry
    def fetch():
        return sf_client.query_all(sf_object_name, field_names, since=since)

    records = fetch()
    log.info(f"        {len(records):,} records retrieved.")

    if not records:
        log.info("        Nothing to load.")
        snow_client.log_sync(
            object_name=sf_object_name, sync_mode=mode, status="SUCCESS",
            rows_loaded=0, started_at=started_at, finished_at=datetime.utcnow(),
        )
        return

    # ── Step 6: Load into Snowflake ───────────────────────────────────────
    if mode == "full":
        log.info(f"  [6/6] Inserting all records into Snowflake...")

        @with_retry
        def load():
            return snow_client.insert_records(table_name, field_names, records)

    else:
        log.info(f"  [6/6] Upserting records into Snowflake (MERGE on Id)...")

        @with_retry
        def load():
            return snow_client.upsert_records(table_name, field_names, records)

    rows_loaded = load()
    finished_at = datetime.utcnow()

    snow_client.log_sync(
        object_name=sf_object_name, sync_mode=mode, status="SUCCESS",
        rows_loaded=rows_loaded, started_at=started_at, finished_at=finished_at,
    )
    log.info(f"        ✓ {rows_loaded:,} rows loaded into '{table_name}'.")


def run(objects, mode):
    """Runs the sync for a list of objects."""
    start_time = datetime.now()
    log.info("=" * 60)
    log.info(f"  Salesforce → Snowflake  |  mode: {mode}")
    log.info("=" * 60)

    sf_client   = SalesforceClient()
    snow_client = SnowflakeClient()

    results = []
    for obj in objects:
        started_at = datetime.utcnow()
        try:
            sync_object(sf_client, obj, snow_client, mode=mode)
            results.append({"object": obj, "rows": 0, "status": "SUCCESS"})
        except Exception as e:
            finished_at = datetime.utcnow()
            log.error(f"  ✗ Failed: '{obj}': {e}")
            snow_client.log_sync(
                object_name=obj, sync_mode=mode, status="FAILED",
                rows_loaded=0, started_at=started_at, finished_at=finished_at,
                error_message=str(e),
            )
            send_failure_alert(obj, e)
            results.append({"object": obj, "rows": 0, "status": f"FAILED: {e}"})

    snow_client.close()

    elapsed = (datetime.now() - start_time).total_seconds()
    success = [r for r in results if r["status"] == "SUCCESS"]
    failed  = [r for r in results if r["status"] != "SUCCESS"]

    log.info("=" * 60)
    log.info(f"  DONE in {elapsed:.0f}s  ✓ {len(success)} succeeded  ✗ {len(failed)} failed")
    if failed:
        log.info(f"  Failed: {[r['object'] for r in failed]}")
    log.info("=" * 60)

    send_success_summary(results, elapsed)
    return results


def main():
    parser = argparse.ArgumentParser(description="Salesforce → Snowflake Connector")
    group  = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--object", help="Sync a single object, e.g. Account")
    group.add_argument("--all", action="store_true", help="Sync all objects in config.py")
    parser.add_argument(
        "--mode",
        choices=["full", "incremental"],
        default=SYNC_MODE,
        help="Sync mode (default from config: %(default)s)",
    )
    args = parser.parse_args()
    objects = SALESFORCE_OBJECTS if args.all else [args.object]
    run(objects, mode=args.mode)


if __name__ == "__main__":
    main()