# SMART GitHub Command Bridge

## Goal
ChatGPT writes a small, structured command to GitHub. A SMART agent already running on the user's Windows PC polls that command, performs an allow-listed market-data action through the Iranian network, and writes the result back to GitHub.

## Important security rule
The bridge does **not** execute arbitrary shell commands from GitHub. The only supported action is currently `fetch_tsetmc`, with a symbol value. Add new actions as explicit Python functions only.

## One-time Windows setup

From the project directory:

```powershell
$env:SMART_GITHUB_REPO="SMART101-12/Smart"
$env:SMART_GITHUB_BRANCH="main"
$env:SMART_GITHUB_TOKEN="<YOUR_GITHUB_TOKEN>"
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m smart.command_agent
```

The token needs permission to read and write repository contents. Never commit the token to GitHub or place it in source files.

## How the loop works

```text
ChatGPT
  -> runtime/command.json
  -> local SMART command agent
  -> TSETMC from the user's Iranian connection
  -> data/smart.db + raw snapshot
  -> runtime/result.json
  -> ChatGPT reads the result from GitHub
```

The local command agent must be running for a command to execute. GitHub cannot wake a sleeping Windows process by itself. For hands-free operation, the agent can later be registered in Windows Task Scheduler to start at login.

## Example command

```json
{
  "request_id": "unique-id",
  "action": "fetch_tsetmc",
  "symbol": "عیار"
}
```

## Result
The result contains the request ID, status, completion timestamp, and the TSETMC adapter response. Raw snapshots remain in the local SQLite database; the GitHub result is the transport/reporting layer.
