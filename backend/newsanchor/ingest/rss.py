"""RSS/Atom ingestion -- the default backbone of NewsAnchor.

Why RSS is the primary adapter rather than a commercial news API:

  * No key, no quota, no per-request cost, no terms forbidding the thing you
    want to build. Most "free tier" news APIs cap at ~100 requests/day and
    forbid production use outright.
  * The publisher is unambiguous. Aggregator APIs frequently hand you an
    article attributed to whichever site re-syndicated it, which quietly
    destroys the source-lean signal this whole app depends on.
  * It degrades gracefully. One dead feed costs you one outlet.

The tradeoffs are real and worth stating: feeds carry headline + blurb rather
than full text, they rot without notice, and coverage of any given outlet is
whatever that outlet felt like publishing. Commercial APIs are wired in as
optional supplements (see gdelt.py, newsapi.py) rather than replacements.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import feedparser
import httpx

from ..models import Article, Source
from .base import FetchResult

USER_AGENT = "NewsAnchor/0.1 (personal news aggregator; +https://github.com/Ahmed7AK/NewsAnchor)"


def _parse_date(entry) -> datetime | None:
    """Feeds lie about dates in creative ways; try the plausible fields."""
    for key in ("published", "updated", "created"):
        raw = entry.get(key)
        if not raw:
            continue
        try:
            dt = parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            continue
        if dt is None:
            continue
        # Naive datetimes from feeds are conventionally UTC.
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)

    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            return datetime(*parsed[:6], tzinfo=UTC)
    return None


def _clean(text: str) -> str:
    """Feed summaries are HTML soup. Strip tags without pulling in a parser."""
    import html
    import re

    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def entries_to_articles(source: Source, feed_bytes: bytes, since: datetime) -> list[Article]:
    """Pure function: bytes in, Articles out. Kept separate so tests need no network."""
    parsed = feedparser.parse(feed_bytes)
    articles: list[Article] = []

    for entry in parsed.entries:
        url = (entry.get("link") or "").strip()
        title = _clean(entry.get("title", ""))
        if not url or not title:
            continue

        published = _parse_date(entry)
        if published is None:
            # Undated entries are usually evergreen boilerplate. Skipping them
            # is safer than assuming "now" and letting them squat at the top
            # of every digest forever.
            continue
        if published < since:
            continue

        articles.append(
            Article(
                source_id=source.id,
                title=title,
                url=url,
                published_at=published,
                summary=_clean(entry.get("summary", ""))[:1200],
                author=_clean(entry.get("author", "")),
            )
        )
    return articles


class RSSAdapter:
    name = "rss"

    def __init__(
        self,
        sources: list[Source],
        *,
        timeout: float = 15.0,
        concurrency: int = 8,
    ) -> None:
        self.sources = sources
        self.timeout = timeout
        self.concurrency = concurrency

    async def _fetch_feed(
        self, client: httpx.AsyncClient, source: Source, url: str, since: datetime
    ) -> FetchResult:
        try:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            return FetchResult(errors=[f"{source.id} <{url}>: {type(exc).__name__}: {exc}"])

        try:
            return FetchResult(articles=entries_to_articles(source, resp.content, since))
        except Exception as exc:  # noqa: BLE001 - see below
            # Intentionally broad. feedparser is lenient but not total, and a
            # single outlet serving malformed XML must cost us that outlet, not
            # the whole morning's digest. The error is surfaced, not swallowed.
            return FetchResult(errors=[f"{source.id} <{url}>: parse failed: {exc}"])

    async def fetch(self, since: datetime) -> FetchResult:
        result = FetchResult()
        sem = asyncio.Semaphore(self.concurrency)

        async with httpx.AsyncClient(
            timeout=self.timeout, headers={"User-Agent": USER_AGENT}
        ) as client:

            async def one(source: Source, url: str) -> FetchResult:
                async with sem:
                    return await self._fetch_feed(client, source, url, since)

            jobs = [one(s, url) for s in self.sources for url in s.feeds]
            for partial in await asyncio.gather(*jobs):
                result.extend(partial)

        # Same story can appear in several feeds of one outlet (world + politics).
        seen: set[str] = set()
        deduped = []
        for article in result.articles:
            if article.id in seen:
                continue
            seen.add(article.id)
            deduped.append(article)
        result.articles = deduped
        return result
