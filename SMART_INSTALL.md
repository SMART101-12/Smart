# SMART — final Windows installation

## What is already implemented
- Iran-side TSETMC collector
- SQLite raw snapshot storage
- data freshness/provenance tracking
- GitHub command queue
- GitHub result and compact snapshot persistence
- allow-listed command execution (`fetch_tsetmc` only)
- `smart start`, `smart stop`, `smart status`, `smart once`
- secure one-time GitHub token storage through Windows Credential Manager
- installer that creates the virtual environment and adds `smart` to the user PATH

## One-time setup
1. Download the repository ZIP from GitHub and extract it.
2. Open PowerShell in the extracted folder.
3. Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\install-smart.ps1
```

4. The installer installs dependencies and asks for a GitHub fine-grained token. The token must be limited to `SMART101-12/Smart` and have Repository permissions: **Contents: Read and write**. GitHub's documentation recommends selecting only the repositories and minimum permissions needed. See the official documentation for fine-grained tokens.
5. Close PowerShell and open a new PowerShell.
6. Start SMART:

```powershell
smart start
```

7. Verify:

```powershell
smart status
```

## Daily use
You do not need to keep ChatGPT connected to the PC. The local SMART agent polls the GitHub command queue. When a command is placed in `runtime/command.json`, the local agent executes the allow-listed action against TSETMC from the user's Iranian connection, saves the raw data locally, and writes a result plus compact snapshot to GitHub.

The assistant can then read the GitHub result and analyze it.

## Security
The local agent does not execute arbitrary PowerShell/cmd commands received from GitHub. Only the explicit market-data action `fetch_tsetmc` is accepted. The GitHub token is stored through Windows Credential Manager rather than being written into the repository.
