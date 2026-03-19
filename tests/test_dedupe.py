"""Dedupe URL normalization (architecture §8.1)."""

import pytest

from job_raider.dedupe import compute_dedupe_id


def test_lowercase_host_and_scheme():
    assert compute_dedupe_id("HTTPS://Example.COM/path?q=1#frag") == "https://example.com/path?q=1"


def test_strip_default_https_port():
    assert compute_dedupe_id("https://example.com:443/foo") == "https://example.com/foo"


def test_strip_default_http_port():
    assert compute_dedupe_id("http://example.com:80/foo") == "http://example.com/foo"


def test_rejects_non_http_scheme():
    with pytest.raises(ValueError, match="http or https"):
        compute_dedupe_id("ftp://example.com/a")
