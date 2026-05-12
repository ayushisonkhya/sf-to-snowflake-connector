"""
snowflake_client.py
===================
Handles everything related to Snowflake:
  - Connecting
  - Running SQL (CREATE TABLE, TRUNCATE, etc.)
  - Bulk loading via write_pandas
  - MERGE upsert: update existing rows + insert new ones in one operation
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

# Staging table suffix — used during MERGE operation
_STAGE_SUFFIX = "_STAGE"


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

    def execute(self, sql):
        """Run any SQL statement."""
        self.cursor.execute(sql)

    # ── insert_records (full refresh) ──────────────────────────────────────

    def insert_records(self, table_name, field_names, records):
        """
        Bulk-loads records using write_pandas.
        Used for full refresh mode (table already truncated before this call).
        Returns number of rows loaded.
        """
        if not records:
            return 0

        df = self._build_dataframe(field_names, records)

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

    # ── upsert_records (incremental MERGE) ────────────────────────────────

    def upsert_records(self, table_name, field_names, records):
        """
        Upserts records using Snowflake MERGE statement.

        How it works:
          1. Load records into a temporary staging table
          2. Run MERGE from staging → target table on Id
             - WHEN MATCHED     → UPDATE all columns
             - WHEN NOT MATCHED → INSERT new row
          3. Drop the staging table

        This means:
          - Existing records get updated if anything changed
          - New records get inserted
          - Deleted records in Salesforce are NOT deleted here
            (use full refresh for that)

        Works automatically for any object — no hardcoding needed.
        Returns number of rows upserted.
        """
        if not records:
            return 0

        table_name  = table_name.upper()
        stage_table = f"{table_name}{_STAGE_SUFFIX}"
        df          = self._build_dataframe(field_names, records)
        columns     = list(df.columns)   # already uppercased

        # ── Step 1: Create staging table (copy structure from target) ──────
        self.cursor.execute(f"""
            CREATE OR REPLACE TEMPORARY TABLE "{stage_table}"
            LIKE "{table_name}"
        """)

        # ── Step 2: Load records into staging table ────────────────────────
        success, _, num_rows, _ = write_pandas(
            conn              = self.conn,
            df                = df,
            table_name        = stage_table,
            database          = SNOW_DATABASE,
            schema            = SNOW_SCHEMA,
            auto_create_table = False,
            overwrite         = False,
            quote_identifiers = False,
        )

        if not success:
            raise RuntimeError(f"write_pandas failed for staging table {stage_table}")

        log.debug(f"    Staged {num_rows:,} rows into {stage_table}")

        # ── Step 3: Build MERGE SQL ────────────────────────────────────────
        #
        # UPDATE clause: set every column except Id and _LOADED_AT
        update_cols = [
            c for c in columns
            if c not in ("ID", "_LOADED_AT")
        ]
        update_clause = ",\n                ".join(
            f'T."{c}" = S."{c}"' for c in update_cols
        )

        # INSERT clause: all columns except _LOADED_AT (it has a DEFAULT)
        insert_cols = [c for c in columns if c != "_LOADED_AT"]
        insert_col_list  = ", ".join(f'"{c}"' for c in insert_cols)
        insert_val_list  = ", ".join(f'S."{c}"' for c in insert_cols)

        merge_sql = f"""
MERGE INTO "{table_name}" AS T
USING "{stage_table}"  AS S
ON T."ID" = S."ID"

WHEN MATCHED THEN UPDATE SET
    {update_clause}

WHEN NOT MATCHED THEN INSERT
    ({insert_col_list})
VALUES
    ({insert_val_list});
""".strip()

        # ── Step 4: Execute MERGE ──────────────────────────────────────────
        self.cursor.execute(merge_sql)
        self.conn.commit()

        # Snowflake returns rows_inserted + rows_updated from MERGE
        merge_result = self.cursor.fetchone()
        rows_inserted = merge_result[0] if merge_result else 0
        rows_updated  = merge_result[1] if merge_result and len(merge_result) > 1 else 0
        log.info(f"    MERGE complete: {rows_inserted:,} inserted, {rows_updated:,} updated")

        # ── Step 5: Drop staging table ─────────────────────────────────────
        self.cursor.execute(f'DROP TABLE IF EXISTS "{stage_table}"')

        return rows_inserted + rows_updated

    # ── get_last_sync_time ────────────────────────────────────────────────

    def get_last_sync_time(self, object_name):
        """
        Returns the last successful sync time for the given object
        as a Salesforce-compatible ISO string, or None if not found.
        """
        self.cursor.execute("""
            SELECT MAX("FINISHED_AT")
            FROM _SYNC_LOG
            WHERE "OBJECT_NAME" = %s
              AND "STATUS"      = 'SUCCESS'
        """, (object_name,))
        row = self.cursor.fetchone()
        if row and row[0]:
            return row[0].strftime("%Y-%m-%dT%H:%M:%SZ")
        return None

    # ── log_sync ──────────────────────────────────────────────────────────

    def log_sync(self, object_name, sync_mode, status, rows_loaded,
                 started_at, finished_at, error_message=None):
        """Writes one row to _SYNC_LOG recording the outcome of a sync."""
        duration = (finished_at - started_at).total_seconds()
        self.cursor.execute("""
            INSERT INTO _SYNC_LOG
                ("OBJECT_NAME","SYNC_MODE","STATUS","ROWS_LOADED",
                 "ERROR_MESSAGE","STARTED_AT","FINISHED_AT","DURATION_SEC")
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            object_name, sync_mode, status, rows_loaded,
            error_message, started_at, finished_at, round(duration, 2),
        ))
        self.conn.commit()

    # ── _ensure_sync_log ──────────────────────────────────────────────────

    def _ensure_sync_log(self):
        """Creates _SYNC_LOG table if it doesn't exist yet."""
        self.cursor.execute(_SYNC_LOG_DDL)

    # ── _build_dataframe ──────────────────────────────────────────────────

    def _build_dataframe(self, field_names, records):
        """
        Builds a cleaned DataFrame from Salesforce records.
        Uppercases column names and cleans values.
        """
        df = pd.DataFrame(records, columns=field_names)
        df = df.apply(lambda col: col.map(self._clean))
        df.columns = [c.upper() for c in df.columns]
        return df

    # ── _clean ────────────────────────────────────────────────────────────

    def _clean(self, val):
        """
        Cleans a value before loading into Snowflake.
        - Converts dicts (compound fields) to strings
        - Converts Salesforce timestamps to plain strings Snowflake accepts
        """
        if val is None:
            return None

        if isinstance(val, dict):
            return str(val)

        if isinstance(val, str) and "T" in val and len(val) >= 19:
            for fmt in (
                "%Y-%m-%dT%H:%M:%S.%f+0000",
                "%Y-%m-%dT%H:%M:%S.%f%z",
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S",
            ):
                try:
                    dt = datetime.strptime(val, fmt)
                    return dt.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue

        return val

    # ── close ─────────────────────────────────────────────────────────────

    def close(self):
        """Close the Snowflake connection."""
        self.cursor.close()
        self.conn.close()
        log.info("Snowflake connection closed.")