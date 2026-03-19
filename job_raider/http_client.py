"""
Shared HTTP session: timeouts, bounded retries, politeness delays (architecture §7).
"""

from __future__ import annotations

import random
import time
import requests

from job_raider import __version__

DEFAULT_TIMEOUT = (30, 30)
# Architecture §7: jitter between requests (ms)
DEFAULT_POLITE_DELAY_MS_RANGE = (750, 1500)
RETRY_BACKOFF_SECONDS = (0.5, 1.5)
MAX_GET_ATTEMPTS = 3

USER_AGENT = f"JobRaider/{__version__} (+https://github.com/job-raider/job-raider)"


class HttpClient:
    """
    Thin wrapper around ``requests`` with global politeness delay and GET retries.

    Delays apply *between* requests (not before the first).
    """

    def __init__(
        self,
        *,
        timeout: tuple[float, float] | float = DEFAULT_TIMEOUT,
        polite_delay_ms_range: tuple[int, int] = DEFAULT_POLITE_DELAY_MS_RANGE,
        session: requests.Session | None = None,
    ) -> None:
        self._timeout = timeout
        self._delay_ms = polite_delay_ms_range
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._first_request = True

    def _polite_wait(self) -> None:
        if self._first_request:
            self._first_request = False
            return
        low, high = self._delay_ms
        delay_s = random.uniform(low / 1000.0, high / 1000.0)
        time.sleep(delay_s)

    def get(self, url: str) -> requests.Response:
        """
        GET with up to ``MAX_GET_ATTEMPTS`` attempts on transient failures.

        Retries on HTTP 429/503 and ``requests.ConnectionError`` with backoff.
        """
        self._polite_wait()
        for attempt in range(MAX_GET_ATTEMPTS):
            try:
                response = self._session.get(url, timeout=self._timeout)
                if response.status_code in (429, 503):
                    if attempt < MAX_GET_ATTEMPTS - 1:
                        time.sleep(RETRY_BACKOFF_SECONDS[attempt])
                        continue
                response.raise_for_status()
                return response
            except requests.ConnectionError:
                if attempt < MAX_GET_ATTEMPTS - 1:
                    time.sleep(RETRY_BACKOFF_SECONDS[attempt])
                    continue
                raise
        raise RuntimeError("HttpClient.get: unreachable")  # pragma: no cover
