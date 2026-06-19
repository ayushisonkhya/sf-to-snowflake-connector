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
├── retry.py                # Retry decorator with exponential backoff
├── alerting.py             # Sends email/Slack alerts on failure
├── scheduler.py            # Runs the sync automatically on a timer
├── Dashboard.py             # Web UI to monitor sync status (FastAPI)
├── requirements.txt        # Python dependencies
└── README.md                # This file
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

## ⚙️ Prerequisites

Python 3.9+
A Salesforce account with API access
A Salesforce Connected App (for OAuth2 login) — provides Consumer Key/Secret
A Snowflake account with a warehouse, database, and schema created
(Optional) A Gmail account with an App Password, for email alerts
(Optional) A Slack workspace with an Incoming Webhook URL, for Slack alerts


### Step 1 — Python

Python 3.11 or higher
Download from python.org
Verify: python3 --version

### Step 2 — Salesforce Account


| What | Where to get it |
|---|---|
| `Username` | Your Salesforce login email |
| `Password` | Your Salesforce password |
| `Security Token` | Salesforce → Avatar (top right) → Settings → Personal → Reset My Security Token → check your email |
| `Connected App` |See setup steps below |
| `Consumer Key` | From your Connected App → Manage Consumer Details |
| `Consumer Secret` | From your Connected App → Manage Consumer Details |

---

Creating a Connected App in Salesforce

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


### Step 3 — Snowflake Account


| What | Where to get it |
|---|---|
| `Account Identifier` | From Snowflake UI → bottom left avatar → Account Details → Account Identifier (e.g. WIQCDYF-DZ97890) |
| `Username` | Your Snowflake login name (shown in Account Details → Login Name) |
| `Password` | Your Snowflake password |
| `Database` |An existing database where tables will be created |
| `Schema` | An existing schema inside that database |
| `Warehouse` | An existing compute warehouse (e.g. COMPUTE_WH) |
| `Role` | A role with CREATE TABLE permission (e.g. ACCOUNTADMIN or SYSADMIN) |


## ▶️ How to Run

### Step 1 — Clone the repository

git clone https://github.com/YOUR_USERNAME/sf-to-snowflake-connector.git
cd sf-to-snowflake-connector


### Step 2 - Install python libraries

```bash
pip3 install -r requirements.txt
```

### Sync a single object

```bash
python connector.py --object Account
python connector.py --object Contact
python connector.py --object Opportunity
```

### Sync all objects listed in config.py

```bash
python connector.py --all
```

### Choose sync mode

```bash
python3 connector.py --object Account --mode full          # truncate + reload everything
python3 connector.py --object Account --mode incremental   # only new/changed records
```

### How it works

For each Salesforce object:

```
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


### Tech Stack


| Tool | Purpose |
|---|---|
| `Python 3.11` | Core language |
| `simple-salesforce` | Salesforce API client |
| `snowflake-connector-python` | Snowflake connection |
| `pandas + write_pandas` |Bulk data loading|
| `FastAPI + Uvicorn` | Web dashboard |

