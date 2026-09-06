"""NewsAPI.org adapter -- optional, and read the caveats before enabling it.

NewsAPI's free "Developer" plan is a prototyping tool, not a foundation:
  * 100 requests/day
  * articles delayed ~24h
  * ~1 month of archive
  * CORS restricted to localhost
  * development use only -- production and commercial use are forbidden

For a personal daily digest the 24h delay is the killer, not the quota. This
adapter exists so you can compare its coverage against the RSS backbone, and
because paid tiers remove the delay if you decide it is worth it.

Requires NEWSAPI_KEY in the environment.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from dateutil import parser as dateparser

from ..models import Article
from .base import FetchResult

ENDPOINT = "https://newsapi.org/v2/top-headlines"


class NewsAPIAdapter:
    name = "newsapi"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        country: str = "us",
        category: str | None = None,
        page_size: int = 100,
        timeout: float = 20.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("NEWSAPI_KEY", "")
        self.country = country
        self.category = category
        self.page_size = min(page_size, 100)
        self.timeout = timeout

    def to_articles(self, payload: dict, since: datetime) -> list[Article]:
        out = []
        for item in payload.get("articles", []) or []:
            url = (item.get("url") or "").strip()
            title = (item.get("title") or "").strip()
            if not url or not title:
                continue
            try:
                published = dateparser.isoparse(item.get("publishedAt", ""))
            except (ValueError, TypeError):
                continue
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            if published < since:
                continue
            domain = urlparse(url).netloc
            out.append(
                Article(
                    source_id=f"newsapi:{domain}",
                    title=title,
                    url=url,
                    published_at=published,
                    summary=(item.get("description") or "")[:1200],
                    author=(item.get("author") or "")[:200],
                )
            )
        return out

    async def fetch(self, since: datetime) -> FetchResult:
        if not self.api_key:
            return FetchResult(errors=["newsapi: NEWSAPI_KEY not set; adapter skipped"])

        params = {"country": self.country, "pageSize": str(self.page_size)}
        if self.category:
            params["category"] = self.category

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    ENDPOINT, params=params, headers={"X-Api-Key": self.api_key}
                )
                resp.raise_for_status()
                payload = resp.json()
        except httpx.HTTPError as exc:
            return FetchResult(errors=[f"newsapi: {type(exc).__name__}: {exc}"])

        if payload.get("status") != "ok":
            return FetchResult(errors=[f"newsapi: {payload.get('message', 'unknown error')}"])
        return FetchResult(articles=self.to_articles(payload, since))
