"""
snowflake_client.py
===================
Handles everything related to Snowflake:
  - Connecting to Snowflake
  - Running SQL statements (CREATE TABLE, INSERT, etc.)
  - Bulk inserting records efficiently

Library used: snowflake-connector-python
Install with:  pip install snowflake-connector-python
"""

import logging
import snowflake.connector
from config import (
    SNOW_ACCOUNT, SNOW_USER, SNOW_PASSWORD,
    SNOW_DATABASE, SNOW_SCHEMA, SNOW_WAREHOUSE, SNOW_ROLE
)

log = logging.getLogger(__name__)

# How many rows to insert in one batch.
# 1000 is a safe default — large enough to be fast, small enough to avoid timeouts.
BATCH_SIZE = 1000


class SnowflakeClient:
    """
    A simple wrapper around the Snowflake Python connector.
    Opens a connection when created, closes it when you call .close().
    """

    def __init__(self):
        log.info("Connecting to Snowflake...")
        self.conn = snowflake.connector.connect(
            account   = SNOW_ACCOUNT,
            user      = SNOW_USER,
            password  = SNOW_PASSWORD,
            database  = SNOW_DATABASE,
            schema    = SNOW_SCHEMA,
            warehouse = SNOW_WAREHOUSE,
            role      = SNOW_ROLE,
        )
        self.cursor = self.conn.cursor()
        log.info("  ✓ Connected to Snowflake.")

    # ── execute ────────────────────────────────────────────────────────────

    def execute(self, sql: str):
        """
        Runs any SQL statement.
        Used for CREATE TABLE, USE statements, etc.
        """
        self.cursor.execute(sql)

    # ── insert_records ─────────────────────────────────────────────────────

    def insert_records(self, table_name: str, field_names: list[str], records: list[dict]):
        """
        Inserts all records into the Snowflake table in batches.

        Example of the SQL it builds:
          INSERT INTO ACCOUNT ("ID", "NAME", "PHONE")
          VALUES (%s, %s, %s)

        The %s placeholders are filled in safely by the connector
        (this prevents SQL injection).
        """
        if not records:
            return

        # Build column list: ["Id", "Name"] → '"ID", "NAME"'
        col_list = ", ".join(f'"{name.upper()}"' for name in field_names)

        # Build placeholders: 3 fields → "%s, %s, %s"
        placeholders = ", ".join(["%s"] * len(field_names))

        insert_sql = f'INSERT INTO {table_name} ({col_list}) VALUES ({placeholders})'

        # Split records into batches and insert one batch at a time
        total    = len(records)
        inserted = 0

        for batch_start in range(0, total, BATCH_SIZE):
            batch = records[batch_start : batch_start + BATCH_SIZE]

            # Convert each record dict to a tuple in the same order as field_names
            # e.g. {"Id": "001...", "Name": "Acme"} → ("001...", "Acme")
            rows = [
                tuple(self._clean(row.get(field)) for field in field_names)
                for row in batch
            ]

            self.cursor.executemany(insert_sql, rows)
            inserted += len(batch)
            log.debug(f"    Inserted {inserted}/{total} rows...")

        self.conn.commit()

    # ── _clean ─────────────────────────────────────────────────────────────

    def _clean(self, val):
        """
        Cleans a value before inserting into Snowflake:
          - Converts nested dicts (e.g. address fields) to plain text
          - Converts Salesforce timestamps like '2026-04-29T08:37:08.000+0000'
            into Snowflake-friendly format '2026-04-29 08:37:08'
        """
        # If it's a nested object (e.g. BillingAddress), convert to string
        if isinstance(val, dict):
            return str(val)

        # If it looks like a Salesforce timestamp, reformat it
        if isinstance(val, str) and 'T' in val and len(val) > 18:
            try:
                # Remove timezone offset and milliseconds
                val = val.replace('+0000', '').replace('Z', '')
                val = val.replace('T', ' ')
                val = val.split('.')[0]   # remove milliseconds
            except Exception:
                pass

        return val

    # ── close ──────────────────────────────────────────────────────────────

    def close(self):
        """Always close the connection when you are done."""
        self.cursor.close()
        self.conn.close()
        log.info("Snowflake connection closed.")
