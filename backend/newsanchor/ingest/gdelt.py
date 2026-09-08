"""GDELT DOC 2.0 adapter -- optional breadth supplement.

GDELT indexes worldwide news in 65+ languages, needs no API key, no
registration, and imposes no documented quota. That makes it uniquely good at
one job NewsAnchor cares about: telling you a story exists that none of your
subscribed outlets ran.

What it is not good at: attribution you can trust for bias scoring. GDELT
reports the domain that published a piece, which is often a syndicator rather
than the originating newsroom. So GDELT articles are ingested for *coverage
detection* and marked as unrated rather than being folded into the lean
histogram as if they were a rated source.

Docs: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
Endpoint is public; be polite about request rate anyway.
"""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx

from ..models import Article
from .base import FetchResult

ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
MAX_RECORDS = 250  # hard ceiling imposed by the API


class GDELTAdapter:
    name = "gdelt"

    def __init__(
        self,
        query: str,
        *,
        timespan: str = "1d",
        max_records: int = 100,
        source_lang: str = "eng",
        timeout: float = 30.0,
    ) -> None:
        self.query = query
        self.timespan = timespan
        self.max_records = min(max_records, MAX_RECORDS)
        self.source_lang = source_lang
        self.timeout = timeout

    def _params(self) -> dict[str, str]:
        query = self.query
        if self.source_lang:
            query = f"{query} sourcelang:{self.source_lang}"
        return {
            "query": query,
            "mode": "ArtList",
            "format": "json",
            "maxrecords": str(self.max_records),
            "timespan": self.timespan,
            "sort": "hybridrel",
        }

    @staticmethod
    def _parse_seendate(raw: str) -> datetime | None:
        # GDELT returns e.g. "20260906T131500Z"
        try:
            return datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        except (TypeError, ValueError):
            return None

    def to_articles(self, payload: dict, since: datetime) -> list[Article]:
        out = []
        for item in payload.get("articles", []) or []:
            url = (item.get("url") or "").strip()
            title = (item.get("title") or "").strip()
            if not url or not title:
                continue
            published = self._parse_seendate(item.get("seendate", ""))
            if published is None or published < since:
                continue
            domain = item.get("domain") or urlparse(url).netloc
            out.append(
                Article(
                    source_id=f"gdelt:{domain}",
                    title=title,
                    url=url,
                    published_at=published,
                    summary="",
                )
            )
        return out

    async def fetch(self, since: datetime) -> FetchResult:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(ENDPOINT, params=self._params())
                resp.raise_for_status()
                # GDELT sometimes returns HTML error pages with a 200.
                payload = resp.json()
        except httpx.HTTPError as exc:
            return FetchResult(errors=[f"gdelt: {type(exc).__name__}: {exc}"])
        except ValueError as exc:
            return FetchResult(errors=[f"gdelt: non-JSON response: {exc}"])

        return FetchResult(articles=self.to_articles(payload, since))
