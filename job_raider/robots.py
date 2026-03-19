"""
Per-run robots.txt gate (architecture §4 step 4, NFR3).
"""

from __future__ import annotations

import logging
import urllib.robotparser
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class RobotsPolicy:
    """
    Cache ``RobotFileParser`` per origin; on fetch failure allow requests (logged).
    """

    def __init__(self, user_agent: str) -> None:
        self._user_agent = user_agent
        self._cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def allowed(self, url: str) -> bool:
        parsed = urlparse(url.strip())
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return True

        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._cache:
            robots_url = f"{origin}/robots.txt"
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(robots_url)
            try:
                rp.read()
                self._cache[origin] = rp
            except Exception as e:
                logger.warning(
                    "Could not fetch robots.txt %s (%s); allowing fetch for this run",
                    robots_url,
                    e,
                )
                self._cache[origin] = None

        rp = self._cache[origin]
        if rp is None:
            return True
        try:
            return rp.can_fetch(self._user_agent, url)
        except Exception as e:
            logger.warning("robots can_fetch failed for %s (%s); allowing", url, e)
            return True
