"""
Optional local Ollama relevance filter for job opportunities.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"
DEFAULT_AI_FILTER_MODEL = "gemma3:4b"


def _build_prompt(title: str, summary: str) -> str:
    body = f"{title}. {summary}".strip()
    return (
        "Rispondi solo YES o NO: questo è un avviso di selezione, bando o opportunità "
        "di lavoro per un esperto esterno, tutor, orientatore o figura professionale? "
        f"Testo: '{body}'"
    )


def _response_contains_yes(text: str) -> bool:
    return "YES" in text.upper()


def is_job_opportunity(title: str, summary: str, model: str = DEFAULT_AI_FILTER_MODEL) -> bool:
    """
    Ask a local Ollama model whether the text describes a job / selection notice.

    Returns True when the model answer contains ``YES``, otherwise False.
    On connection or API errors, logs a warning and returns True (fail-open).
    """
    prompt = _build_prompt(title, summary or "")
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    try:
        resp = requests.post(OLLAMA_GENERATE_URL, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError, TypeError) as e:
        logger.warning("Ollama ai_filter unavailable (%s); keeping item", e)
        return True

    answer = data.get("response") if isinstance(data, dict) else None
    if not isinstance(answer, str):
        logger.warning("Ollama ai_filter returned unexpected payload; keeping item")
        return True

    return _response_contains_yes(answer)
