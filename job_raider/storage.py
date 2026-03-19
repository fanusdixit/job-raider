"""
Atomic persistence for ``results.json`` (architecture ADR-06, Epic 3 Story 3.5).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from job_raider.merge import document_to_json_dict
from job_raider.models import ResultsDocument


def write_results_atomic(path: str | Path, doc: ResultsDocument, *, indent: int = 2) -> None:
    """
    Write ``doc`` to ``path`` using a temp file in the same directory + ``os.replace``.

    UTF-8, ensure_ascii=False for Italian text.
    """
    path = Path(path)
    payload = document_to_json_dict(doc)
    text = json.dumps(payload, indent=indent, ensure_ascii=False) + "\n"
    data = text.encode("utf-8")

    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        dir=directory,
        prefix=".results.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
