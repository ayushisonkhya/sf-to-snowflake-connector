"""
Salesforce → Snowflake Connector
=================================
This connector does 3 things:
  1. Connects to Salesforce and reads object schemas + data
  2. Creates matching tables in Snowflake (if they don't exist)
  3. Loads the data into those tables

How to use:
  python connector.py --object Account
  python connector.py --object Contact
  python connector.py --all          ← syncs all objects listed in config.py
"""

import argparse
import logging
from datetime import datetime

from salesforce_client import SalesforceClient
from snowflake_client import SnowflakeClient
from schema_mapper import map_sf_field_to_snowflake
from config import SALESFORCE_OBJECTS

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Core sync function ─────────────────────────────────────────────────────────

def sync_object(sf_client: SalesforceClient, sf_object_name: str, snow_client: SnowflakeClient):
    """
    Full sync pipeline for one Salesforce object:
      Step 1 → Describe the object to get its fields/schema
      Step 2 → Build a CREATE TABLE statement for Snowflake
      Step 3 → Execute the CREATE TABLE (skipped if table already exists)
      Step 4 → Query all records from Salesforce
      Step 5 → Insert records into Snowflake
    """
    log.info(f"─── Starting sync for: {sf_object_name} ───")

    # ── Step 1: Get Salesforce schema ──────────────────────────────────────
    log.info(f"  [1/5] Fetching schema from Salesforce for '{sf_object_name}'...")
    sf_fields = sf_client.describe_object(sf_object_name)
    log.info(f"        Found {len(sf_fields)} fields.")

    # ── Step 2: Build Snowflake column definitions ─────────────────────────
    log.info(f"  [2/5] Mapping Salesforce field types → Snowflake column types...")
    snowflake_columns = []
    for field in sf_fields:
        col_name  = field["name"].upper()           # Snowflake likes UPPERCASE
        col_type  = map_sf_field_to_snowflake(field["type"])
        snowflake_columns.append(f'    "{col_name}"  {col_type}')

    # We also add a metadata column to track when the row was loaded
    snowflake_columns.append('    "_LOADED_AT"  TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP()')

    columns_sql = ",\n".join(snowflake_columns)
    table_name  = sf_object_name.upper()

    create_sql = f"""
CREATE TABLE IF NOT EXISTS {table_name} (
{columns_sql}
);
""".strip()

    # ── Step 3: Create table in Snowflake ─────────────────────────────────
    log.info(f"  [3/5] Creating table '{table_name}' in Snowflake (if not exists)...")
    snow_client.execute(create_sql)
    log.info(f"        Table ready.")

    # ── Step 4: Query records from Salesforce ─────────────────────────────
    log.info(f"  [4/5] Querying records from Salesforce...")
    field_names = [f["name"] for f in sf_fields]
    records     = sf_client.query_all(sf_object_name, field_names)
    log.info(f"        Retrieved {len(records)} records.")

    if not records:
        log.info("        Nothing to load. Done.")
        return

    # ── Step 5: Insert into Snowflake ─────────────────────────────────────
    log.info(f"  [5/5] Loading records into Snowflake...")
    snow_client.insert_records(table_name, field_names, records)
    log.info(f"        ✓ {len(records)} rows inserted into '{table_name}'.")


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Salesforce → Snowflake Connector")
    group  = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--object", help="Sync a single Salesforce object, e.g. Account")
    group.add_argument("--all",    action="store_true", help="Sync all objects in config.py")
    args = parser.parse_args()

    start_time = datetime.now()
    log.info("=" * 60)
    log.info("  Salesforce → Snowflake Connector  STARTED")
    log.info("=" * 60)

    # Initialise both clients (connections are made here)
    sf_client   = SalesforceClient()
    snow_client = SnowflakeClient()

    objects_to_sync = SALESFORCE_OBJECTS if args.all else [args.object]

    success, failed = [], []
    for obj in objects_to_sync:
        try:
            sync_object(sf_client, obj, snow_client)
            success.append(obj)
        except Exception as e:
            log.error(f"  ✗ Failed to sync '{obj}': {e}")
            failed.append(obj)

    snow_client.close()

    # ── Summary ───────────────────────────────────────────────────────────
    elapsed = (datetime.now() - start_time).seconds
    log.info("=" * 60)
    log.info(f"  DONE in {elapsed}s   ✓ {len(success)} succeeded   ✗ {len(failed)} failed")
    if failed:
        log.info(f"  Failed objects: {failed}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
