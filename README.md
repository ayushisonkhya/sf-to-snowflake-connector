# Salesforce to Snowflake Connector

A Python pipeline that automatically syncs data from Salesforce objects (Account, Contact, Lead, Opportunity, Case, etc.) into Snowflake tables. It supports full and incremental loads, automatic retries on failure, email/Slack alerting, scheduled runs, and a live web dashboard to monitor everything.

---

## 📁 Project Structure

```
sf_to_snowflake/
├── config.py              # All credentials and settings (single source of truth)
├── salesforce_client.py   # Connects to and queries Salesforce
├── snowflake_client.py    # Connects to and loads data into Snowflake
├── connector.py           # Main pipeline — orchestrates the full sync
├── schema_mapper.py       # Translates Salesforce field types → Snowflake types
├── retry.py               # Retry decorator with exponential backoff
├── alerting.py            # Sends email/Slack alerts on failure
├── scheduler.py           # Runs the sync automatically on a timer
├── Dashboard.py           # Web UI to monitor sync status (FastAPI)
├── requirements.txt       # Python dependencies
└── README.md              # This file
```


## How it works-architecture

                         config.py
                  (credentials & settings)
                          |
                          v
                    connector.py
                  (main orchestrator)
                    /            \
                   v              v
        salesforce_client.py   snowflake_client.py
        (auth + SOQL query)    (create table, insert/MERGE)
                   \              /
                    v            v
                  schema_mapper.py
              (SF field type → Snowflake type)
                          |
                          v
                      retry.py
            (wraps risky calls, retries on failure)
                          |
                          v
                     alerting.py
            (emails/Slack message if it still fails)

      scheduler.py  -------calls------->  connector.py (on a timer)
      Dashboard.py  -------calls------->  connector.py (on button click)
---

## Prerequisites

- Python 3.9+  
- A Salesforce account with API access  
- A Salesforce Connected App (for OAuth2 login) — provides Consumer Key/Secret  
- A Snowflake account with a warehouse, database, and schema created  
- (Optional) A Gmail account with an App Password, for email alerts  
- (Optional) A Slack workspace with an Incoming Webhook URL, for Slack alerts  

### Set up

## Step 0. Create a Salesforce Developer Edition Account

1. Go to developer.salesforce.com/signup
2. Fill in the form:
     First Name / Last Name: your name
     Email: your work or personal email
     Role: Developer
     Company: your company name
     Username: must be in email format but does not need to be a real email address
3. Click "Sign me up"
4. Check your email → click "Verify Account"
5. Set your password — save it somewhere safe
6. You are in! Your org URL will look like:
      https://orgfarm-XXXXXXXX.develop.lightning.force.com

## Step 1. Clone the repo and install dependencies
      git clone https://github.com/ayushisonkhya/sf-to-snowflake-connector
      cd sf-to-snowflake-connector
      pip install -r requirements.txt


## Step 2. Salesforce Account

1. Go to Setup → search "Connected Apps" in Quick Find → click Create Connected App
2. Fill in:
     Connected App Name: SnowflakeConnector
     Contact Email: your email
3. If you are not able to see create connected app then open https://orgfarm-c4f22785dd-dev-ed.develop.lightning.force.com/app/mgmt/forceconnectedapps/forceAppEdit.apexp in URL (in my case) otherwise https://YOUR-ORG-URL.develop.lightning.force.com/app/mgmt/forceconnectedapps/forceAppEdit.apexp.
4. Check "Enable OAuth Settings"
5. Callback URL: https://localhost:8080/callback
6. Selected OAuth Scopes: add Full access (full) and Perform requests at any time
7. Click Save — wait 2–10 minutes for it to activate
8. Go to Setup → OAuth and OpenID Connect Settings → if its ON move to next steps otherwise turn it ON.
9. Click Manage Consumer Details to get your Consumer Key and Consumer Secret.
10. Add it to Config.py.

## Step 3. Fill in config.py

| What | Where to get it |
|---|---|
| `Username` | Your Salesforce login email |
| `Password` | Your Salesforce password |
| `Security Token` | Salesforce → Avatar (top right) → Settings → Personal → Reset My Security Token → check your email |
| `Domain` | login for production<br>test for sandbox |
| `Consumer Key` | From your Connected App → Manage Consumer Details |
| `Consumer Secret` | From your Connected App → Manage Consumer Details |



## Step 4. Snowflake Account


| What | Where to get it |
|---|---|
| `Account Identifier` | From Snowflake UI → bottom left avatar → Account Details → Account Identifier (e.g. WIQCDYF-DZ97890) |
| `Username` | Your Snowflake login name (shown in Account Details → Login Name) |
| `Password` | Your Snowflake password |
| `Database` |An existing database where tables will be created |
| `Schema` | An existing schema inside that database |
| `Warehouse` | An existing compute warehouse (e.g. COMPUTE_WH) |
| `Role` | A role with CREATE TABLE permission (e.g. ACCOUNTADMIN or SYSADMIN) |


## Running the connector

### Sync a single object

python connector.py --object Account  
python connector.py --object Contact  
python connector.py --object Opportunity  


### Sync all objects listed in config.py

python connector.py --all  

### Choose sync mode

python3 connector.py --object Account --mode full    
python3 connector.py --object Account --mode incremental

### How it works

For each Salesforce object:

Step 1 → Fetch schema from Salesforce
         (what fields does Account have? Id, Name, Phone, BillingCity, ...)

Step 2 → Map field types
         (Salesforce "currency" → Snowflake "NUMBER(18,2)")

Step 3 → Create table in Snowflake (if it doesn't exist)
         (CREATE TABLE IF NOT EXISTS ACCOUNT ...)

Step 4 → Full mode:  TRUNCATE the table
         Incremental: get last successful sync time from _SYNC_LOG

Step 5 → Query records from Salesforce
         Full:        SELECT * FROM Account
         Incremental: SELECT * FROM Account WHERE SystemModstamp >= <last sync>

Step 6 → Load into Snowflake
         Full:        bulk INSERT using write_pandas
         Incremental: MERGE (update existing rows + insert new ones)

### Automatic retries
Any Salesforce or Snowflake call wrapped in @with_retry automatically retries up to RETRY_MAX_ATTEMPTS (default 3) times, with exponential backoff (RETRY_BASE_DELAY doubling each attempt — e.g. 2s, 4s, 8s) before giving up.

@with_retry  
def fetch():  
    return sf_client.query_all(...)  

If all attempts fail, the exception is raised, caught by connector.py, logged as FAILED in _SYNC_LOG, and an alert is sent.

### Alerting (email / Slack)

Disabled by default. Enable in config.py:

ALERT_EMAIL_ENABLED  = True  
ALERT_EMAIL_FROM     = "your.gmail@gmail.com"  
ALERT_EMAIL_TO       = "your.gmail@gmail.com"  
ALERT_EMAIL_PASSWORD = "your-16-character-gmail-app-password"  


Gmail requires an App Password, not your normal password. Generate one at myaccount.google.com/apppasswords (requires 2-Step Verification to be turned on first).


### Web dasboard
A real-time web UI to monitor sync status and trigger syncs manually.

Run the dashboard

pip3 install fastapi uvicorn
python3 dashboard.py

Then open http://localhost:8000 in your browser.

Features
Live status card per object (rows loaded, duration, last run time)
Run incremental or full refresh per object from the UI
Full sync history table
Auto-refreshes every 10 seconds


### Adding a new Salesforce object to sync

No code changes needed — just add it to the list in config.py:  

SALESFORCE_OBJECTS = [  
    "Account",  
    "Contact",  
    "Lead",  
    "Opportunity",  
    "Case",  
    "My_Custom_Object__c",    # custom objects end in __c  
]  

The connector automatically describes its schema, maps its field types, creates its table, and syncs it — the same as any built-in object.


### Tech Stack


| Tool | Purpose |
|---|---|
| `Python 3.11` | Core language |
| `simple-salesforce` | Salesforce API client |
| `snowflake-connector-python` | Snowflake connection |
| `pandas + write_pandas` |Bulk data loading|
| `FastAPI + Uvicorn` | Web dashboard |

