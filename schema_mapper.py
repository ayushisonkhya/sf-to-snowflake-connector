"""
schema_mapper.py
================
Translates Salesforce field types into Snowflake column types.

Salesforce has its own type system (e.g. "currency", "picklist").
Snowflake has a different type system (e.g. NUMBER, VARCHAR).
This file is the "dictionary" between the two.

If you find a Salesforce type that is missing, just add it to the
SALESFORCE_TO_SNOWFLAKE dictionary below.

IMPORTANT: All keys must be lowercase — the lookup always calls .lower()
           on the incoming Salesforce type before matching.
"""

# ── Type mapping dictionary ────────────────────────────────────────────────────
#
# Key   = Salesforce field type (lowercase)
# Value = Snowflake column type (SQL syntax)
#

SALESFORCE_TO_SNOWFLAKE = {
    # Text types
    "string"          : "VARCHAR(16777216)",   # max Snowflake VARCHAR
    "textarea"        : "VARCHAR(16777216)",
    "email"           : "VARCHAR(255)",
    "phone"           : "VARCHAR(40)",
    "url"             : "VARCHAR(1024)",
    "picklist"        : "VARCHAR(255)",
    "multipicklist"   : "VARCHAR(4096)",
    "combobox"        : "VARCHAR(255)",
    "encryptedstring" : "VARCHAR(1300)",

    # ID / reference types
    "id"              : "VARCHAR(18)",
    "reference"       : "VARCHAR(18)",

    # Number types
    "int"             : "NUMBER(18, 0)",
    "integer"         : "NUMBER(18, 0)",
    "double"          : "FLOAT",
    "currency"        : "NUMBER(18, 2)",
    "percent"         : "NUMBER(18, 2)",

    # Boolean
    "boolean"         : "BOOLEAN",

    # Date / time types
    "date"            : "DATE",
    "datetime"        : "TIMESTAMP_NTZ",       # NTZ = No Time Zone stored
    "time"            : "TIME",

    # Binary / base64 — store as text since Snowflake has no blob type
    "base64"          : "VARCHAR(16777216)",

    # Address is a compound type — store as text
    "address"         : "VARCHAR(1000)",

    # Location (geolocation) — store as text
    "location"        : "VARCHAR(255)",

    # FIX: was "anyType" (mixed-case) → never matched after .lower()
    # Now correctly stored as "anytype" to match the lowercased lookup
    "anytype"         : "VARIANT",

    # Added missing types that Salesforce returns in the wild
    "calculated"      : "VARCHAR(16777216)",   # formula fields
    "masterrecord"    : "VARCHAR(18)",          # master-detail relationship ID
    "complexvalue"    : "VARIANT",              # structured/nested data
    "junctionidlist"  : "VARCHAR(4096)",        # many-to-many junction
    "datacategorygroupreference": "VARCHAR(255)",
    "long"            : "NUMBER(18, 0)",
}


def map_sf_field_to_snowflake(sf_type: str) -> str:
    """
    Given a Salesforce field type string (e.g. "currency"),
    returns the matching Snowflake column type (e.g. "NUMBER(18, 2)").

    Lookup is always case-insensitive (.lower()) so mixed-case types
    like "anyType" or "DateTime" are handled correctly.

    If the type is unknown, returns VARCHAR(16777216) as a safe fallback
    and logs a warning so you know to add it to the mapping above.
    """
    snowflake_type = SALESFORCE_TO_SNOWFLAKE.get(sf_type.lower())

    if snowflake_type is None:
        import logging
        logging.getLogger(__name__).warning(
            f"  ⚠ Unknown Salesforce type '{sf_type}' — defaulting to VARCHAR(16777216). "
            f"Consider adding it to schema_mapper.py."
        )
        return "VARCHAR(16777216)"

    return snowflake_type
