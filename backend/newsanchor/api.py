"""FastAPI app serving the digest to the React frontend."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import db, llm
from .balance import pollable_leans, roster_warnings
from .digest import Digest, DigestOptions, run_digest
from .models import LEAN_LABELS, Source, Story
from .sources import active_sources, default_registry, spectrum_coverage

app = FastAPI(title="NewsAnchor", version="0.1.0")

# The frontend dev server. Tighten or drop this if you deploy anywhere real.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# One in-flight refresh at a time: a digest run hits several dozen feeds and
# there is nothing to gain from two of them racing.
_refresh_lock = asyncio.Lock()


def _serialise_article(article, registry: dict[str, Source]) -> dict[str, Any]:
    source = registry.get(article.source_id)

    # The newsroom that did the reporting, which for syndicated copy is the
    # wire rather than the outlet that reprinted it. Every position claim the
    # UI makes is keyed off this, so that the coverage list cannot contradict
    # the histogram sitting directly above it.
    newsroom_id = article.syndicated_from or article.source_id
    newsroom = registry.get(newsroom_id)

    return {
        "id": article.id,
        "title": article.title,
        "url": article.url,
        "summary": article.summary,
        "published_at": article.published_at.isoformat(),
        "syndicated_from": article.syndicated_from,
        "source": {
            "id": article.source_id,
            "name": source.name if source else article.source_id,
            "lean": source.lean if source else None,
            "lean_label": source.lean_label if source else "unrated",
            "country": source.country if source else None,
            "tier": source.tier if source else None,
            "state_affiliated": bool(source.state_affiliated) if source else False,
            "paywall": source.paywall if source else None,
        },
        "newsroom": {
            "id": newsroom_id,
            "name": newsroom.name if newsroom else newsroom_id,
            "lean": newsroom.lean if newsroom else None,
            "lean_label": newsroom.lean_label if newsroom else "unrated",
        },
    }


def _serialise_story(story: Story, registry: dict[str, Source]) -> dict[str, Any]:
    articles = [_serialise_article(a, registry) for a in story.articles]

    # The side-by-side view: one representative article per spectrum position,
    # which is the whole point of "balanced exposure".
    #
    # Grouped by the *reporting newsroom's* position, and collapsed to one
    # entry per newsroom. Grouping by the reprinting outlet instead would put
    # a single AP dispatch under both "lean-left" and "right" and make the
    # story look cross-spectrum when it is one wire report.
    by_lean: dict[str, list[dict[str, Any]]] = {}
    seen_newsrooms: set[str] = set()
    for item in sorted(articles, key=lambda i: i["published_at"]):
        newsroom_id = item["newsroom"]["id"]
        if newsroom_id in seen_newsrooms:
            continue
        seen_newsrooms.add(newsroom_id)
        # How many outlets carried this newsroom's copy, so the UI can say
        # "reprinted by 3" rather than implying three separate reports.
        item = {
            **item,
            "carried_by": sum(1 for a in articles if a["newsroom"]["id"] == newsroom_id),
        }
        by_lean.setdefault(item["newsroom"]["lean_label"], []).append(item)

    lead = min(story.articles, key=lambda a: a.published_at)
    return {
        "id": story.id,
        "headline": max(story.articles, key=lambda a: len(a.title)).title,
        "lead_source_id": lead.syndicated_from or lead.source_id,
        "newest": story.newest.isoformat(),
        "articles": articles,
        "by_lean": by_lean,
        "lean_histogram": {LEAN_LABELS[k]: v for k, v in story.lean_histogram.items()},
        "unrated_newsrooms": story.unrated_newsrooms,
        "coverage_gaps": [LEAN_LABELS[g] for g in story.coverage_gaps],
        "balance_score": story.balance_score,
        "diversity_score": story.diversity_score,
        "prominence": story.prominence,
        "rank_score": story.rank_score,
        "neutral_summary": story.neutral_summary,
        "source_count": len(story.source_ids),
        "reprint_count": sum(1 for a in story.articles if a.syndicated_from),
    }


def _serialise_digest(digest: Digest, registry: dict[str, Source]) -> dict[str, Any]:
    return {
        "generated_at": digest.generated_at.isoformat(),
        "window_start": digest.window_start.isoformat(),
        "article_count": digest.article_count,
        "source_count": digest.source_count,
        "warnings": digest.warnings,
        "errors": digest.errors,
        "llm_summaries_enabled": llm.is_available(),
        "stories": [_serialise_story(s, registry) for s in digest.stories],
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    registry = default_registry()
    return {
        "status": "ok",
        "sources_configured": len(registry),
        "sources_active": len(active_sources(registry)),
        "llm_summaries_enabled": llm.is_available(),
    }


@app.get("/api/sources")
def sources() -> dict[str, Any]:
    registry = default_registry()
    active = active_sources(registry)
    return {
        "sources": [
            {
                "id": s.id,
                "name": s.name,
                "homepage": s.homepage,
                "lean": s.lean,
                "lean_label": s.lean_label,
                "tier": s.tier,
                "country": s.country,
                "paywall": s.paywall,
                "state_affiliated": s.state_affiliated,
                "enabled": s.enabled,
                "feed_count": len(s.feeds),
                "notes": s.notes,
            }
            for s in sorted(registry.values(), key=lambda s: (s.lean is None, s.lean or 0, s.name))
        ],
        "spectrum": {LEAN_LABELS[lean]: ids for lean, ids in spectrum_coverage(registry).items()},
        "warnings": roster_warnings(active),
        "pollable_leans": sorted(pollable_leans(active)),
    }


@app.get("/api/digest")
def get_digest(digest_id: int | None = None) -> dict[str, Any]:
    """Return a stored digest. Does not fetch -- use POST /api/refresh for that."""
    registry = default_registry()
    with db.connect() as conn:
        digest = db.load_digest(conn, digest_id)
    if digest is None:
        raise HTTPException(
            status_code=404,
            detail="No digest stored yet. POST /api/refresh or run `newsanchor refresh`.",
        )
    return _serialise_digest(digest, registry)


@app.post("/api/refresh")
async def refresh(
    window_hours: int = Query(24, ge=1, le=168),
    min_sources: int = Query(1, ge=1, le=10),
    include_state_affiliated: bool = False,
    summarise: bool = False,
) -> dict[str, Any]:
    """Fetch every active feed and rebuild the digest. Slow -- tens of seconds."""
    if _refresh_lock.locked():
        raise HTTPException(status_code=409, detail="A refresh is already running.")

    async with _refresh_lock:
        registry = default_registry()
        options = DigestOptions(
            window_hours=window_hours,
            min_sources=min_sources,
            include_state_affiliated=include_state_affiliated,
        )
        digest = await run_digest(options, registry=registry)

        if summarise:
            await asyncio.to_thread(llm.summarise_digest, digest.stories, registry)

        with db.connect() as conn:
            db.save_digest(conn, digest)

    return _serialise_digest(digest, registry)


@app.get("/api/reading-balance")
def reading_balance(days: int = Query(30, ge=1, le=365)) -> dict[str, Any]:
    """What your feed has actually been made of lately.

    Per-story balance scores can all look healthy while the feed as a whole is
    dominated by three newsrooms. This endpoint is the check on that.

    Counts are per reporting newsroom, so wire copy read on three different
    sites counts once, against the wire. `by_source` keeps its name for
    compatibility but its ids are newsroom ids.
    """
    registry = default_registry()
    with db.connect() as conn:
        counts = db.reading_balance(conn, days)

    total = sum(counts.values())
    by_lean: dict[str, int] = {}
    by_country: dict[str, int] = {}
    for source_id, n in counts.items():
        source = registry.get(source_id)
        by_lean[source.lean_label if source else "unrated"] = (
            by_lean.get(source.lean_label if source else "unrated", 0) + n
        )
        country = source.country if source else "??"
        by_country[country] = by_country.get(country, 0) + n

    return {
        "days": days,
        "total_articles": total,
        "by_source": [
            {
                "id": sid,
                "name": registry[sid].name if sid in registry else sid,
                "count": n,
                "share": round(n / total, 4) if total else 0.0,
            }
            for sid, n in counts.items()
        ],
        "by_lean": by_lean,
        "by_country": by_country,
        "generated_at": datetime.now(UTC).isoformat(),
    }
