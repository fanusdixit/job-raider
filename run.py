#!/usr/bin/env python3
"""
Job Raider entry point (Phase 1).

E1: validates `searches.yaml` and exits. Full pipeline arrives in E5.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(description="Job Raider — job/tender monitor")
    parser.add_argument(
        "config",
        nargs="?",
        default="searches.yaml",
        help="Path to searches.yaml (default: ./searches.yaml)",
    )
    args = parser.parse_args(argv)

    # Local import so `python run.py` works before editable install if needed
    from job_raider.config import load_searches
    from job_raider.exceptions import ConfigError

    path = Path(args.config)
    try:
        cfg = load_searches(path)
    except ConfigError as e:
        print(str(e), file=sys.stderr)
        return 1
    except OSError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"Configuration OK: {path.resolve()}")
    print(f"  Searches loaded: {len(cfg.searches)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
