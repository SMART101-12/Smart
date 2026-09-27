# SMART Iran Data Agent

## Purpose
Run this small collector on a machine/network that can reach Iranian market sources. The agent is only responsible for collection and persistence; analysis remains in SMART.

## Windows quick start

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements-iran-agent.txt
$env:PYTHONPATH = "src"
$env:SMART_SOURCE_URL = "<VERIFIED_SOURCE_ENDPOINT>"
py -m smart.iran_agent --symbol "عیار" --source "tsetmc"
```

Replace `<VERIFIED_SOURCE_ENDPOINT>` with an endpoint that you have verified from the Iranian network. Do not put credentials or API keys in this file.

## What gets stored
- symbol
- source
- UTC observation timestamp
- market date
- raw JSON payload

The snapshot is stored in `data/smart.db` using the existing `SnapshotStore`.

## Important
The current agent deliberately does **not** hard-code an unverified TSETMC endpoint. TSETMC has multiple historical/current endpoints and access behavior can vary by network. Once a working endpoint is confirmed from the user's Iranian connection, it should be added as a dedicated adapter and tested against real responses.
