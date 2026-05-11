"""
alerting.py
===========
Sends failure alerts via Email and/or Slack.

Enable in .env:
    ALERT_EMAIL_ENABLED=true
    ALERT_SLACK_ENABLED=true

For Gmail, use an App Password (not your regular password):
    Google Account → Security → 2-Step Verification → App passwords
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

import requests

from config import (
    ALERT_EMAIL_ENABLED, ALERT_EMAIL_FROM, ALERT_EMAIL_TO,
    ALERT_EMAIL_PASSWORD, ALERT_SMTP_HOST, ALERT_SMTP_PORT,
    ALERT_SLACK_ENABLED, ALERT_SLACK_WEBHOOK_URL,
)

log = logging.getLogger(__name__)


def send_failure_alert(object_name: str, error: Exception):
    """
    Called when a sync fails. Sends alerts to all enabled channels.
    Safe to call even if alerting is disabled — it's a no-op.
    """
    if not ALERT_EMAIL_ENABLED and not ALERT_SLACK_ENABLED:
        return

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    message   = (
        f"Salesforce → Snowflake sync FAILED\n"
        f"Object   : {object_name}\n"
        f"Error    : {error}\n"
        f"Time     : {timestamp}"
    )

    if ALERT_EMAIL_ENABLED:
        _send_email(
            subject=f"[SF→Snowflake] Sync failed: {object_name}",
            body=message,
        )

    if ALERT_SLACK_ENABLED:
        _send_slack(message)


def send_success_summary(results: list[dict], elapsed_seconds: float):
    """
    Sends a summary alert after a full sync run.
    Only fires if at least one object failed (to avoid alert fatigue).
    """
    failed = [r for r in results if r["status"] != "SUCCESS"]
    if not failed:
        return   # all good — no alert needed

    if not ALERT_EMAIL_ENABLED and not ALERT_SLACK_ENABLED:
        return

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [f"Sync run completed with errors — {timestamp}",
             f"Duration : {elapsed_seconds:.0f}s", ""]

    for r in results:
        icon = "✓" if r["status"] == "SUCCESS" else "✗"
        lines.append(f"  {icon} {r['object']:<30} {r['rows']:>8,} rows   {r['status']}")

    message = "\n".join(lines)

    if ALERT_EMAIL_ENABLED:
        _send_email(subject="[SF→Snowflake] Sync completed with errors", body=message)

    if ALERT_SLACK_ENABLED:
        _send_slack(message)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _send_email(subject: str, body: str):
    try:
        msg = MIMEMultipart()
        msg["From"]    = ALERT_EMAIL_FROM
        msg["To"]      = ALERT_EMAIL_TO
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(ALERT_SMTP_HOST, ALERT_SMTP_PORT) as server:
            server.starttls()
            server.login(ALERT_EMAIL_FROM, ALERT_EMAIL_PASSWORD)
            server.sendmail(ALERT_EMAIL_FROM, ALERT_EMAIL_TO, msg.as_string())

        log.info(f"  📧 Email alert sent to {ALERT_EMAIL_TO}")
    except Exception as e:
        log.error(f"  Failed to send email alert: {e}")


def _send_slack(message: str):
    try:
        payload = {"text": f"```{message}```"}
        response = requests.post(ALERT_SLACK_WEBHOOK_URL, json=payload, timeout=10)
        if response.status_code == 200:
            log.info("  💬 Slack alert sent.")
        else:
            log.error(f"  Slack alert failed: HTTP {response.status_code}")
    except Exception as e:
        log.error(f"  Failed to send Slack alert: {e}")