"""
salesforce_client.py
====================
Connects to Salesforce via OAuth2 (Username-Password Flow).
Supports incremental sync via SystemModstamp filtering.
"""

import logging
import requests
from simple_salesforce import Salesforce
from config import (
    SF_USERNAME, SF_PASSWORD, SF_SECURITY_TOKEN,
    SF_CONSUMER_KEY, SF_CONSUMER_SECRET, SF_DOMAIN,
)

log = logging.getLogger(__name__)


class SalesforceClient:

    def __init__(self):
        log.info("Connecting to Salesforce via OAuth2...")

        token_url = f"https://{SF_DOMAIN}.salesforce.com/services/oauth2/token"
        payload = {
            "grant_type"    : "password",
            "client_id"     : SF_CONSUMER_KEY,
            "client_secret" : SF_CONSUMER_SECRET,
            "username"      : SF_USERNAME,
            "password"      : SF_PASSWORD + SF_SECURITY_TOKEN,
        }

        response = requests.post(token_url, data=payload)
        result   = response.json()

        if "access_token" not in result:
            error = result.get("error_description", result)
            raise Exception(f"Salesforce OAuth2 login failed: {error}")

        self.sf = Salesforce(
            instance_url = result["instance_url"],
            session_id   = result["access_token"],
        )
        log.info(f"  ✓ Connected. Instance: {result['instance_url']}")

    # ── describe_object ────────────────────────────────────────────────────

    def describe_object(self, object_name: str) -> list[dict]:
        """Returns queryable field definitions for a Salesforce object."""
        sf_object   = getattr(self.sf, object_name)
        description = sf_object.describe()

        return [
            field for field in description["fields"]
            if field.get("name") and not field.get("compoundFieldName")
        ]

    # ── query_all ──────────────────────────────────────────────────────────

    def query_all(
        self,
        object_name: str,
        field_names: list[str],
        since:       str | None = None,
    ) -> list[dict]:
        """
        Fetches records for the given object.

        If `since` is provided (ISO timestamp string), only records where
        SystemModstamp >= since are returned — this is incremental sync.

        If `since` is None, all records are returned — full load.

        Salesforce paginates automatically via simple-salesforce query_all.
        """
        fields_str = ", ".join(field_names)
        soql = f"SELECT {fields_str} FROM {object_name}"

        if since:
            # SystemModstamp tracks every create and update — reliable watermark
            soql += f" WHERE SystemModstamp >= {since}"

        log.debug(f"  SOQL: {soql[:140]}...")

        result  = self.sf.query_all(soql)
        records = [
            {k: v for k, v in row.items() if k != "attributes"}
            for row in result["records"]
        ]
        return records