"""
HTML listing adapter (BeautifulSoup + selectors).

Implemented in Epic 4; placeholder keeps registry and imports stable for Epic 2.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from job_raider.exceptions import AdapterError
from job_raider.models import RawItem
from job_raider.sources.base import SourceContext

if TYPE_CHECKING:
    from job_raider.http_client import HttpClient


class HtmlSelectorsAdapter:
    name = "html_selectors"
    supports_native_region = False

    def fetch(self, ctx: SourceContext, http: HttpClient) -> list[RawItem]:
        raise AdapterError(
            f"{ctx.source_label}: html_selectors adapter is not implemented yet (Epic 4)"
        )
