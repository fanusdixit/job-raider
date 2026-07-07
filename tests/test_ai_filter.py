"""Tests for local Ollama ai_filter (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from job_raider.ai_filter import (
    DEFAULT_AI_FILTER_MODEL,
    OLLAMA_GENERATE_URL,
    is_job_opportunity,
)


def test_is_job_opportunity_yes_response() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"response": "YES"}
    with patch("job_raider.ai_filter.requests.post", return_value=mock_resp) as post:
        assert is_job_opportunity("Bando tutor", "Selezione esperto esterno") is True
    post.assert_called_once()
    call = post.call_args
    assert call.args[0] == OLLAMA_GENERATE_URL
    payload = call.kwargs["json"]
    assert payload["model"] == DEFAULT_AI_FILTER_MODEL
    assert payload["stream"] is False
    assert "Bando tutor" in payload["prompt"]
    assert "Selezione esperto esterno" in payload["prompt"]


def test_is_job_opportunity_no_response() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"response": "NO"}
    with patch("job_raider.ai_filter.requests.post", return_value=mock_resp):
        assert is_job_opportunity("Inaugurazione scuola", "Evento istituzionale") is False


def test_is_job_opportunity_yes_case_insensitive() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"response": "yes, bando"}
    with patch("job_raider.ai_filter.requests.post", return_value=mock_resp):
        assert is_job_opportunity("Avviso", "") is True


def test_is_job_opportunity_connection_error_fail_open() -> None:
    with patch(
        "job_raider.ai_filter.requests.post",
        side_effect=requests.ConnectionError("refused"),
    ):
        assert is_job_opportunity("Titolo", "testo") is True


def test_is_job_opportunity_http_error_fail_open() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = requests.HTTPError("500")
    with patch("job_raider.ai_filter.requests.post", return_value=mock_resp):
        assert is_job_opportunity("Titolo", "testo") is True


def test_is_job_opportunity_missing_response_fail_open() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {}
    with patch("job_raider.ai_filter.requests.post", return_value=mock_resp):
        assert is_job_opportunity("Titolo", "testo") is True


def test_is_job_opportunity_custom_model() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"response": "NO"}
    with patch("job_raider.ai_filter.requests.post", return_value=mock_resp) as post:
        is_job_opportunity("T", "S", model="llama3.2")
    assert post.call_args.kwargs["json"]["model"] == "llama3.2"
