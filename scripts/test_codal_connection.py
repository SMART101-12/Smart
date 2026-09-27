"""Run real Codal diagnostics before expanding the extraction pipeline."""
import argparse
import json
from pathlib import Path

from smart.codal import connection_test


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol", nargs="?", default="فولاد")
    parser.add_argument("--output", type=Path, default=Path("runtime/codal_connection"))
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=12)
    args = parser.parse_args()
    result = connection_test(args.symbol, args.output, attempts=args.attempts, timeout=args.timeout)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
