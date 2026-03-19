#!/usr/bin/env python3
"""
Job Raider CLI (Phase 1 / Epic 5).

``python run.py`` loads ``searches.yaml``, fetches sources, writes ``results.json`` and ``index.html``.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(
        description="Job Raider — monitor job/tender listings and refresh the local dashboard",
    )
    parser.add_argument(
        "config",
        nargs="?",
        default="searches.yaml",
        help="Path to searches.yaml (default: ./searches.yaml)",
    )
    parser.add_argument(
        "--results",
        default="results.json",
        help="Output JSON path (default: ./results.json)",
    )
    parser.add_argument(
        "--index",
        default="index.html",
        help="Output dashboard path (default: ./index.html)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Debug logging on stderr",
    )
    args = parser.parse_args(argv)

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(levelname)s] %(message)s",
        stream=sys.stderr,
        force=True,
    )

    from job_raider.pipeline import run

    return run(
        config_path=Path(args.config),
        results_path=Path(args.results),
        index_path=Path(args.index),
    )


if __name__ == "__main__":
    raise SystemExit(main())
