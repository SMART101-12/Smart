"""Background runner for SMART historical gap recovery."""
from __future__ import annotations

import os
from .gap_recovery import run


def main() -> None:
    symbols = [s.strip() for s in os.getenv("SMART_GAP_SYMBOLS", "پالایش").split(",") if s.strip()]
    if not symbols:
        raise SystemExit("SMART_GAP_SYMBOLS must contain at least one symbol")
    run(symbols)


if __name__ == "__main__":
    main()
