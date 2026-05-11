"""
snowflake_client.py
===================
Handles everything related to Snowflake:
  - Connecting
  - Running SQL (CREATE TABLE, TRUNCATE, etc.)
  - Bulk loading via write_pandas (fast)
  - Sync log: records every run in _SYNC_LOG table
"""

import logging
from datetime import datetime

import pandas as pd
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas

from config import (
    SNOW_ACCOUNT, SNOW_USER, SNOW_PASSWORD,
    SNOW_DATABASE, SNOW_SCHEMA, SNOW_WAREHOUSE, SNOW_ROLE,
)

log = logging.getLogger(__name__)

# SQL to create the sync log table (created once, never dropped)
_SYNC_LOG_DDL = """
CREATE TABLE IF NOT EXISTS _SYNC_LOG (
    "ID"            NUMBER AUTOINCREMENT PRIMARY KEY,
    "OBJECT_NAME"   VARCHAR(255),
    "SYNC_MODE"     VARCHAR(20),
    "STATUS"        VARCHAR(20),
    "ROWS_LOADED"   NUMBER,
    "ERROR_MESSAGE" VARCHAR(16777216),
    "STARTED_AT"    TIMESTAMP_NTZ,
    "FINISHED_AT"   TIMESTAMP_NTZ,
    "DURATION_SEC"  NUMBER(10,2)
);
""".strip()


class SnowflakeClient:

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
        self._ensure_sync_log()

    # ── execute ────────────────────────────────────────────────────────────

    def execute(self, sql: str):
        """Run any SQL statement (CREATE, TRUNCATE, USE, etc.)."""
        self.cursor.execute(sql)

    # ── insert_records ─────────────────────────────────────────────────────

    def insert_records(self, table_name: str, field_names: list[str], records: list[dict]) -> int:
        """
        Bulk-loads records using write_pandas (Parquet staging → COPY INTO).
        Returns number of rows loaded.
        """
        if not records:
            return 0

        df = pd.DataFrame(records, columns=field_names)
        df = df.apply(lambda col: col.map(self._clean))
        df.columns = [c.upper() for c in df.columns]

        success, num_chunks, num_rows, _ = write_pandas(
            conn              = self.conn,
            df                = df,
            table_name        = table_name.upper(),
            database          = SNOW_DATABASE,
            schema            = SNOW_SCHEMA,
            auto_create_table = False,
            overwrite         = False,
            quote_identifiers = False,
        )

        if not success:
            raise RuntimeError(f"write_pandas failed for table {table_name}")

        log.debug(f"    write_pandas: {num_rows:,} rows in {num_chunks} chunk(s)")
        return num_rows

    # ── get_last_sync_time ─────────────────────────────────────────────────

    def get_last_sync_time(self, object_name: str) -> str | None:
        """
        Returns the FINISHED_AT timestamp of the last successful sync
        for the given object, as a Salesforce-compatible ISO string.
        Returns None if no successful sync has been recorded yet.
        """
        self.cursor.execute("""
            SELECT MAX("FINISHED_AT")
            FROM _SYNC_LOG
            WHERE "OBJECT_NAME" = %s
              AND "STATUS"      = 'SUCCESS'
        """, (object_name,))
        row = self.cursor.fetchone()
        if row and row[0]:
            # Format as Salesforce SOQL datetime: 2026-01-15T10:30:00Z
            return row[0].strftime("%Y-%m-%dT%H:%M:%SZ")
        return None

    # ── log_sync ───────────────────────────────────────────────────────────

    def log_sync(
        self,
        object_name:   str,
        sync_mode:     str,
        status:        str,
        rows_loaded:   int,
        started_at:    datetime,
        finished_at:   datetime,
        error_message: str = None,
    ):
        """
        Writes one row to _SYNC_LOG recording the outcome of a sync.
        This is your full run history — never truncated.
        """
        duration = (finished_at - started_at).total_seconds()
        self.cursor.execute("""
            INSERT INTO _SYNC_LOG
                ("OBJECT_NAME","SYNC_MODE","STATUS","ROWS_LOADED",
                 "ERROR_MESSAGE","STARTED_AT","FINISHED_AT","DURATION_SEC")
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            object_name,
            sync_mode,
            status,
            rows_loaded,
            error_message,
            started_at,
            finished_at,
            round(duration, 2),
        ))
        self.conn.commit()

    # ── _ensure_sync_log ───────────────────────────────────────────────────

    def _ensure_sync_log(self):
        """Creates _SYNC_LOG table if it doesn't exist yet."""
        self.cursor.execute(_SYNC_LOG_DDL)

    # ── _clean ─────────────────────────────────────────────────────────────

    def _clean(self, val):
        """
        Cleans a value before loading:
          - dicts (compound fields) → string
          - Salesforce ISO timestamps → Python datetime (no tz)
        """
        if val is None:
            return None

        if isinstance(val, dict):
            return str(val)

        if isinstance(val, str) and "T" in val and len(val) >= 19:
            for fmt in (
                "%Y-%m-%dT%H:%M:%S.%f%z",
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S",
            ):
                try:
                    return datetime.strptime(val, fmt).replace(tzinfo=None)
                except ValueError:
                    continue

        return val

    # ── close ──────────────────────────────────────────────────────────────

    def close(self):
        self.cursor.close()
        self.conn.close()
        log.info("Snowflake connection closed.")