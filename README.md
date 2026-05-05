# Salesforce → Snowflake Connector

Automatically reads Salesforce objects, creates matching tables in Snowflake,
and loads the data — all with one command.

---

## 📁 Project Structure

```
sf_to_snowflake/
│
├── connector.py          ← Main script (run this)
├── salesforce_client.py  ← Talks to Salesforce
├── snowflake_client.py   ← Talks to Snowflake
├── schema_mapper.py      ← Converts SF types → Snowflake types
├── config.py             ← Your credentials & settings
└── requirements.txt      ← Python libraries needed
```

---

## ⚙️ Setup (do this once)

### Step 1 — Install Python libraries

Open your terminal and run:

```bash
pip install -r requirements.txt
```

### Step 2 — Fill in your credentials

Open `config.py` and fill in:

| Variable | Where to find it |
|---|---|
| `SF_USERNAME` | Your Salesforce login email |
| `SF_PASSWORD` | Your Salesforce password |
| `SF_SECURITY_TOKEN` | Salesforce → Settings → Personal → Reset My Security Token |
| `SNOW_ACCOUNT` | From your Snowflake URL: `https://ACCOUNT.snowflakecomputing.com` |
| `SNOW_USER` | Your Snowflake username |
| `SNOW_PASSWORD` | Your Snowflake password |
| `SNOW_DATABASE` | The Snowflake database where tables will be created |
| `SNOW_WAREHOUSE` | Your Snowflake compute warehouse name |

---

## ▶️ How to Run

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

---

## 🔄 What happens when you run it?

For each Salesforce object:

```
Step 1 → Ask Salesforce: "What fields does Account have?"
           (Id, Name, Phone, BillingCity, CreatedDate, ...)

Step 2 → Map each field type to Snowflake type
           (string → VARCHAR, currency → NUMBER(18,2), ...)

Step 3 → Run CREATE TABLE IF NOT EXISTS ACCOUNT (...) in Snowflake
           (skipped automatically if table already exists)

Step 4 → Query all Account records from Salesforce

Step 5 → Insert all records into Snowflake in batches of 1000
```

---

## 🧩 Adding More Objects

Open `config.py` and add the object name to `SALESFORCE_OBJECTS`:

```python
SALESFORCE_OBJECTS = [
    "Account",
    "Contact",
    "YourCustomObject__c",   ← add custom objects like this
]
```

---

## ⚠️ Common Errors

| Error | Fix |
|---|---|
| `INVALID_LOGIN` | Check username / password / security token in config.py |
| `Object not found` | Check the exact API name in Salesforce (it's case-sensitive) |
| `250001` Snowflake error | Check account name format: `xy12345.us-east-1` |
| `Insufficient privileges` | Make sure your Snowflake role has CREATE TABLE permission |
