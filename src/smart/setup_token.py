"""One-time secure GitHub token setup for SMART on Windows."""
from __future__ import annotations

import getpass
import sys

import keyring
import requests

SERVICE = "SMART-GitHub"
USERNAME = "github-token"


def main() -> None:
    print("SMART GitHub authentication setup")
    print("Create a fine-grained token for SMART101-12/Smart with Contents: Read and write.")
    token = getpass.getpass("Paste GitHub token (input hidden): ").strip()
    if not token:
        raise SystemExit("No token entered.")
    r = requests.get(
        "https://api.github.com/repos/SMART101-12/Smart",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        timeout=20,
    )
    if r.status_code != 200:
        raise SystemExit(f"GitHub authentication failed: HTTP {r.status_code}")
    keyring.set_password(SERVICE, USERNAME, token)
    print("GitHub token saved in Windows Credential Manager.")
    print("The token is not written to the SMART repository or project files.")


if __name__ == "__main__":
    main()
