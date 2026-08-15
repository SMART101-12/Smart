"""User-facing SMART local agent CLI.

Usage after installation:
    smart start
    smart stop
    smart status
    smart once
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "runtime"
PID_FILE = RUNTIME / "agent.pid"
LOG_FILE = RUNTIME / "agent.log"


def _pid() -> int | None:
    try:
        return int(PID_FILE.read_text().strip())
    except (OSError, ValueError):
        return None


def _running(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def start() -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    pid = _pid()
    if _running(pid):
        print(f"SMART is already running (PID {pid}).")
        return
    py = Path(sys.executable)
    cmd = [str(py), "-m", "smart.command_agent"]
    with LOG_FILE.open("a", encoding="utf-8") as log:
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    print(f"SMART started (PID {proc.pid}).")


def stop() -> None:
    pid = _pid()
    if not pid or not _running(pid):
        PID_FILE.unlink(missing_ok=True)
        print("SMART is not running.")
        return
    try:
        os.kill(pid, 15)
    except OSError:
        pass
    PID_FILE.unlink(missing_ok=True)
    print("SMART stopped.")


def status() -> None:
    pid = _pid()
    print("SMART: RUNNING" if _running(pid) else "SMART: STOPPED")
    if pid:
        print(f"PID: {pid}")
    print(f"Log: {LOG_FILE}")


def once() -> None:
    from .command_agent import run_once
    request_id = run_once()
    print(f"Processed request: {request_id or 'none'}")


def main() -> None:
    command = sys.argv[1].lower() if len(sys.argv) > 1 else "status"
    commands = {"start": start, "stop": stop, "status": status, "once": once}
    if command not in commands:
        raise SystemExit("Usage: smart {start|stop|status|once}")
    commands[command]()


if __name__ == "__main__":
    main()
