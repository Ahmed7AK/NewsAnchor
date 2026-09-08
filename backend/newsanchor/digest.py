"""The pipeline: fetch -> annotate -> cluster -> score -> order."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from . import wires
from .balance import (
    enforce_source_diversity,
    pollable_leans,
    roster_warnings,
    score_story,
)
from .cluster import DEFAULT_DISTANCE_THRESHOLD, cluster_articles
from .ingest import RSSAdapter
from .ingest.base import FetchResult
from .models import Article, Source, Story
from .sources import active_sources, default_registry


@dataclass
class DigestOptions:
    window_hours: int = 24
    min_sources: int = 1
    distance_threshold: float = DEFAULT_DISTANCE_THRESHOLD
    include_state_affiliated: bool = False
    max_stories: int = 40
    max_source_share: float = 0.30
    balance_weight: float = 0.35
    diversity_weight: float = 0.25


@dataclass
class Digest:
    generated_at: datetime
    window_start: datetime
    stories: list[Story] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    article_count: int = 0
    source_count: int = 0


def build_digest(
    articles: list[Article],
    sources: list[Source],
    registry: dict[str, Source],
    options: DigestOptions,
    *,
    now: datetime | None = None,
    fetch_errors: list[str] | None = None,
) -> Digest:
    """Pure assembly step -- no network. Given articles, produce the ranked feed."""
    now = now or datetime.now(UTC)
    window_start = now - timedelta(hours=options.window_hours)

    wires.annotate(articles)

    stories = cluster_articles(
        articles,
        distance_threshold=options.distance_threshold,
        min_sources=options.min_sources,
    )

    pollable = pollable_leans(sources)
    for story in stories:
        score_story(
            story,
            registry,
            pollable,
            now=now,
            balance_weight=options.balance_weight,
            diversity_weight=options.diversity_weight,
        )

    stories = enforce_source_diversity(stories, max_share=options.max_source_share)

    return Digest(
        generated_at=now,
        window_start=window_start,
        stories=stories[: options.max_stories],
        warnings=roster_warnings(sources),
        errors=list(fetch_errors or []),
        article_count=len(articles),
        source_count=len({a.source_id for a in articles}),
    )


async def run_digest(
    options: DigestOptions | None = None,
    *,
    registry: dict[str, Source] | None = None,
    extra_adapters: list | None = None,
    now: datetime | None = None,
) -> Digest:
    """Fetch live and build. This is the one function that touches the network."""
    options = options or DigestOptions()
    registry = registry or default_registry()
    now = now or datetime.now(UTC)
    window_start = now - timedelta(hours=options.window_hours)

    sources = active_sources(registry, include_state_affiliated=options.include_state_affiliated)

    result = FetchResult()
    result.extend(await RSSAdapter(sources).fetch(window_start))

    for adapter in extra_adapters or []:
        result.extend(await adapter.fetch(window_start))

    return build_digest(
        result.articles,
        sources,
        registry,
        options,
        now=now,
        fetch_errors=result.errors,
    )
