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
GAP_PID_FILE = RUNTIME / "gap_recovery.pid"
LOG_FILE = RUNTIME / "agent.log"
GAP_LOG_FILE = RUNTIME / "gap_recovery.log"


def _read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text().strip())
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


def _start_process(module: str, log_file: Path, pid_file: Path) -> int:
    py = Path(sys.executable)
    with log_file.open("a", encoding="utf-8") as log:
        proc = subprocess.Popen(
            [str(py), "-m", module],
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    pid_file.write_text(str(proc.pid), encoding="utf-8")
    return proc.pid


def _stop_process(pid_file: Path) -> None:
    pid = _read_pid(pid_file)
    if pid and _running(pid):
        try:
            os.kill(pid, 15)
        except OSError:
            pass
    pid_file.unlink(missing_ok=True)


def start() -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    pid = _read_pid(PID_FILE)
    if not _running(pid):
        pid = _start_process("smart.command_agent", LOG_FILE, PID_FILE)
        print(f"SMART started (PID {pid}).")
    else:
        print(f"SMART is already running (PID {pid}).")

    gap_pid = _read_pid(GAP_PID_FILE)
    if not _running(gap_pid):
        gap_pid = _start_process("smart.gap_recovery_agent", GAP_LOG_FILE, GAP_PID_FILE)
        print(f"SMART gap recovery started (PID {gap_pid}).")
    else:
        print(f"SMART gap recovery is already running (PID {gap_pid}).")


def stop() -> None:
    _stop_process(GAP_PID_FILE)
    _stop_process(PID_FILE)
    print("SMART stopped.")


def status() -> None:
    pid = _read_pid(PID_FILE)
    gap_pid = _read_pid(GAP_PID_FILE)
    print("SMART: RUNNING" if _running(pid) else "SMART: STOPPED")
    if pid:
        print(f"PID: {pid}")
    print("Gap recovery: RUNNING" if _running(gap_pid) else "Gap recovery: STOPPED")
    if gap_pid:
        print(f"Gap PID: {gap_pid}")
    print(f"Log: {LOG_FILE}")
    print(f"Gap log: {GAP_LOG_FILE}")


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
