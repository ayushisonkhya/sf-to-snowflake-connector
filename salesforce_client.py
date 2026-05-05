"""
salesforce_client.py
====================
Connects to Salesforce using OAuth2 (Username-Password Flow).
This works on Developer Edition orgs where SOAP API is disabled.
"""

import logging
import requests
from simple_salesforce import Salesforce
from config import (
    SF_USERNAME, SF_PASSWORD, SF_SECURITY_TOKEN,
    SF_CONSUMER_KEY, SF_CONSUMER_SECRET, SF_DOMAIN
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

        access_token = result["access_token"]
        instance_url = result["instance_url"]

        log.info(f"  Got access token. Instance: {instance_url}")

        self.sf = Salesforce(
            instance_url = instance_url,
            session_id   = access_token,
        )

        log.info("  ✓ Connected to Salesforce via OAuth2.")

    # ── describe_object ────────────────────────────────────────────────────

    def describe_object(self, object_name: str) -> list[dict]:
        """
        Returns a list of field definitions for the given Salesforce object.

        Each item in the list looks like:
          { "name": "AccountNumber", "type": "string", "length": 40, ... }

        We skip fields that cannot be queried (e.g. compound address fields).
        """
        # getattr(self.sf, "Account") gives us the Account SObject
        sf_object = getattr(self.sf, object_name)
        description = sf_object.describe()

        # Filter to only queryable fields
        queryable_fields = [
            field for field in description["fields"]
            if field.get("name") and not field.get("compoundFieldName")
        ]

        return queryable_fields

    # ── query_all ──────────────────────────────────────────────────────────

    def query_all(self, object_name: str, field_names: list[str]) -> list[dict]:
        """
        Fetches ALL records for the given object.

        Builds a SOQL query like:
          SELECT Id, Name, Email FROM Contact

        Handles pagination automatically (Salesforce returns max 2000 rows
        per page; simple-salesforce fetches all pages for us).
        """
        # Join field names into a comma-separated string for SOQL
        fields_str = ", ".join(field_names)
        soql = f"SELECT {fields_str} FROM {object_name}"

        log.debug(f"  Running SOQL: {soql[:120]}...")  # show first 120 chars

        result = self.sf.query_all(soql)

        # result["records"] is a list of dicts, each dict is one row.
        # Salesforce adds an "attributes" key to every record — we remove it.
        records = []
        for row in result["records"]:
            clean_row = {k: v for k, v in row.items() if k != "attributes"}
            records.append(clean_row)

        return records
