"""
config.py
=========
All your credentials and settings live here. test test

This file is SAFE to commit to Git — it contains NO real passwords,
only the names of environment variables to read at runtime.

Each person running this pipeline creates their own local `.env` file
(never committed — it's in .gitignore) with their own real credentials.
See `.env.example` in this repo for the list of variables you need to set.
"""

import os
from dotenv import load_dotenv

load_dotenv()  # reads variables from a local .env file, if present


def _require(key: str) -> str:
    """Fetch a required env var, or fail loudly with a clear message."""
    value = os.getenv(key)
    if value is None or value == "":
        raise RuntimeError(
            f"Missing required environment variable: {key}. "
            f"Did you create a .env file? See .env.example for the full list."
        )
    return value


# ── Salesforce credentials ─────────────────────────────────────────────────────

SF_USERNAME       = _require("SF_USERNAME")
SF_PASSWORD       = _require("SF_PASSWORD")
SF_SECURITY_TOKEN = _require("SF_SECURITY_TOKEN")
                    # ↑ Found in Salesforce: Settings → Personal → Reset My Security Token

SF_DOMAIN         = os.getenv("SF_DOMAIN", "login")
                    # Use "login"  for Production / Developer Edition
                    # Use "test"   for Sandbox

# From your Connected App → Setup → App Manager → SnowflakeConnector → Manage Consumer Details
SF_CONSUMER_KEY    = _require("SF_CONSUMER_KEY")
SF_CONSUMER_SECRET = _require("SF_CONSUMER_SECRET")


# ── Snowflake credentials ──────────────────────────────────────────────────────

SNOW_ACCOUNT   = _require("SNOW_ACCOUNT")
                 # ↑ e.g. "xy12345.us-east-1" — find it in your Snowflake URL

SNOW_USER      = _require("SNOW_USER")
SNOW_PASSWORD  = _require("SNOW_PASSWORD")
SNOW_DATABASE  = os.getenv("SNOW_DATABASE",  "SNOWFLAKE_LEARNING_DB")   # the DB to create tables in
SNOW_SCHEMA    = os.getenv("SNOW_SCHEMA",    "MYSCHEMA")                # schema inside the DB
SNOW_WAREHOUSE = os.getenv("SNOW_WAREHOUSE", "COMPUTE_WH")              # your compute warehouse
SNOW_ROLE      = os.getenv("SNOW_ROLE",      "ACCOUNTADMIN")            # role with CREATE TABLE access


# ── Salesforce objects to sync (used when you run: python connector.py --all) ──

SALESFORCE_OBJECTS = [
    "Account"
    # "Contact",
    # "Lead",
    # "Opportunity",
    # "Case",
    # Add more Salesforce object names here as needed
    # "My_Custom_Object__c",
    # Full list: https://developer.salesforce.com/docs/atlas.en-us.object_reference.meta/object_reference/
]


# ── Sync mode ──────────────────────────────────────────────────────────────────
# "full"        → truncate + reload everything every run
# "incremental" → only fetch records created/modified since last successful run

SYNC_MODE = os.getenv("SYNC_MODE", "incremental")

# ── Scheduling ─────────────────────────────────────────────────────────────────

SCHEDULE_INTERVAL_HOURS = int(os.getenv("SCHEDULE_INTERVAL_HOURS", "1"))

# ── Alerting ───────────────────────────────────────────────────────────────────

ALERT_EMAIL_ENABLED  = os.getenv("ALERT_EMAIL_ENABLED",  "true").lower() == "true"
ALERT_EMAIL_FROM     = os.getenv("ALERT_EMAIL_FROM", "")
ALERT_EMAIL_TO       = os.getenv("ALERT_EMAIL_TO", "")
ALERT_EMAIL_PASSWORD = os.getenv("ALERT_EMAIL_PASSWORD", "")   # Gmail app password
ALERT_SMTP_HOST      = os.getenv("ALERT_SMTP_HOST", "smtp.gmail.com")
ALERT_SMTP_PORT      = int(os.getenv("ALERT_SMTP_PORT", "587"))

ALERT_SLACK_ENABLED     = os.getenv("ALERT_SLACK_ENABLED",     "false").lower() == "true"
ALERT_SLACK_WEBHOOK_URL = os.getenv("ALERT_SLACK_WEBHOOK_URL", "")

# ── Retry logic ────────────────────────────────────────────────────────────────

RETRY_MAX_ATTEMPTS = int(os.getenv("RETRY_MAX_ATTEMPTS", "3"))
RETRY_BASE_DELAY   = float(os.getenv("RETRY_BASE_DELAY", "1.0"))  # seconds, doubles each attempt


# ── How this works ─────────────────────────────────────────────────────────────
#
# 1. Copy `.env.example` to `.env` in this same folder.
# 2. Fill in YOUR OWN real credentials in `.env` (never commit this file).
# 3. Run the pipeline as normal — config.py will load them automatically.
#
# This file (config.py) never contains real passwords, so it's safe to
# share, commit, and review.