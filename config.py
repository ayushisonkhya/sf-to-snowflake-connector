"""
config.py
=========
All your credentials and settings live here.

⚠️  IMPORTANT:
    Never commit this file to Git with real passwords.
    Use environment variables in production (see bottom of this file).

For now, just fill in your values directly below for local testing.
"""

import os

# ── Salesforce credentials ─────────────────────────────────────────────────────

SF_USERNAME       = os.getenv("SF_USERNAME",       "ayushi.sonkhya.9749c4e41343@agentforce.com")
SF_PASSWORD       = os.getenv("SF_PASSWORD",       "connector@123")
SF_SECURITY_TOKEN = os.getenv("SF_SECURITY_TOKEN", "IDpOYpOSR2lFxuD6xkm6wvAY")
                    # ↑ Found in Salesforce: Settings → Personal → Reset My Security TokenID

SF_DOMAIN         = os.getenv("SF_DOMAIN", "login")
                    # Use "login"  for Production / Developer Edition
                    # Use "test"   for Sandbox

# From your Connected App → Setup → App Manager → SnowflakeConnector → Manage Consumer Details
SF_CONSUMER_KEY    = os.getenv("SF_CONSUMER_KEY",    "3MVG9WVXk15qiz1Jojs_5kaOM0gk1_hNsPwokI6JH7vdZGpc40tQtPFDTYnYki93d.eVI9X6ZXzikuTs_B0jT")
SF_CONSUMER_SECRET = os.getenv("SF_CONSUMER_SECRET", "F2FC4DDAE66484D432FD4ADA4665EB13DF3B7C700FF12E1433C593FA32B7B80F")


# ── Snowflake credentials ──────────────────────────────────────────────────────

SNOW_ACCOUNT   = os.getenv("SNOW_ACCOUNT",   "LPBWTLH-YC25782")
                 # ↑ e.g. "xy12345.us-east-1" — find it in your Snowflake URL

SNOW_USER      = os.getenv("SNOW_USER",      "sftosnowflake1")
SNOW_PASSWORD  = os.getenv("SNOW_PASSWORD",  "Connector@1234")
SNOW_DATABASE  = os.getenv("SNOW_DATABASE",  "SNOWFLAKE_LEARNING_DB")       # the DB to create tables in
SNOW_SCHEMA    = os.getenv("SNOW_SCHEMA",    "MYSCHEMA")              # schema inside the DB
SNOW_WAREHOUSE = os.getenv("SNOW_WAREHOUSE", "COMPUTE_WH")         # your compute warehouse
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

SYNC_MODE = "incremental"




# ── Sync mode ──────────────────────────────────────────────────────────────────
# "full"        → truncate + reload everything every run
# "incremental" → only fetch records created/modified since last successful run
 
SYNC_MODE = os.getenv("SYNC_MODE", "incremental")
 
# ── Scheduling ─────────────────────────────────────────────────────────────────
 
SCHEDULE_INTERVAL_HOURS = int(os.getenv("SCHEDULE_INTERVAL_HOURS", "1"))
 
# ── Alerting ───────────────────────────────────────────────────────────────────
 
ALERT_EMAIL_ENABLED  = os.getenv("ALERT_EMAIL_ENABLED",  "true").lower() == "true"
ALERT_EMAIL_FROM     = os.getenv("ALERT_EMAIL_FROM",     "ayushi.sonkhya@atrium.ai")
ALERT_EMAIL_TO       = os.getenv("ALERT_EMAIL_TO",       "ayushi.sonkhya@atrium.ai")
ALERT_EMAIL_PASSWORD = os.getenv("ALERT_EMAIL_PASSWORD", "hofe snxe keum fzrq")   # Gmail app password
ALERT_SMTP_HOST      = os.getenv("ALERT_SMTP_HOST",      "smtp.gmail.com")
ALERT_SMTP_PORT      = int(os.getenv("ALERT_SMTP_PORT",  "587"))
 
ALERT_SLACK_ENABLED     = os.getenv("ALERT_SLACK_ENABLED",     "false").lower() == "true"
ALERT_SLACK_WEBHOOK_URL = os.getenv("ALERT_SLACK_WEBHOOK_URL", "")
 
# ── Retry logic ────────────────────────────────────────────────────────────────
 
RETRY_MAX_ATTEMPTS = int(os.getenv("RETRY_MAX_ATTEMPTS", "3"))
RETRY_BASE_DELAY   = float(os.getenv("RETRY_BASE_DELAY", "1.0"))  # seconds, doubles each attempt
# ── How to use environment variables instead of hardcoding ────────────────────
#
# On Mac/Linux, run these in your terminal before running the connector:
#
#   export SF_USERNAME="me@company.com"
#   export SF_PASSWORD="mypassword"
#   export SF_SECURITY_TOKEN="abc123"
#   export SNOW_ACCOUNT="xy12345.us-east-1"
#   export SNOW_USER="myuser"
#   export SNOW_PASSWORD="mypassword"
#
# On Windows (Command Prompt):
#   set SF_USERNAME=me@company.com
#   set SF_PASSWORD=mypassword
#
# This way your passwords are never written in any file.