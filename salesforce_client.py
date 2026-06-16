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

        #    # When Salesforce receives your login request, it sends back a JSON response that looks like this:
        #  json

   # "access_token": "00D...",
   # "instance_url": "https://orgfarm-c4f22785dd-dev-ed.develop.my.salesforce.com",
   # "id":           "https://login.salesforce.com/id/...",
   # "token_type":   "Bearer",
   # "issued_at":    "1718450100000",
   # "signature":    "abc123..."
   # Salesforce automatically includes instance_url in this response — it's the unique URL of your specific Salesforce org.


        if "access_token" not in result:
            raise Exception(f"Salesforce login failed: {result.get('error_description', result)}")
        self.sf = Salesforce(
            instance_url=result["instance_url"],
            session_id=result["access_token"],
        )
        log.info(f"  ✓ Connected. Instance: {result['instance_url']}")

    def describe_object(self, object_name):
        sf_object   = getattr(self.sf, object_name)
        description = sf_object.describe()
        queryable_fields = [
            field for field in description["fields"]
            if field.get("name")
            and field.get("type") != "address"
          
        ]
        print("FIELDS:", [f["name"] for f in queryable_fields])
        return queryable_fields

    def query_all(self, object_name, field_names, since=None):
        fields_str = ", ".join(field_names)
        soql = f"SELECT {fields_str} FROM {object_name}"
        if since:
            soql += f" WHERE SystemModstamp >= {since}"
        log.debug(f"  SOQL: {soql[:140]}...")
        result = self.sf.query_all(soql)
        return [
            {k: v for k, v in row.items() if k != "attributes"}
            for row in result["records"]
        ]
    


