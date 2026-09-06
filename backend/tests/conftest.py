from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from newsanchor.models import Article, Source

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


def make_source(sid: str, lean, *, country="US", tier="national", **kw) -> Source:
    return Source(
        id=sid,
        name=sid.upper(),
        homepage=f"https://{sid}.example",
        feeds=(f"https://{sid}.example/rss",),
        lean=lean,
        country=country,
        tier=tier,
        **kw,
    )


@pytest.fixture
def registry() -> dict[str, Source]:
    sources = [
        make_source("leftmag", -2),
        make_source("leftpaper", -1),
        make_source("centerwire", 0, tier="wire"),
        make_source("rightpaper", 1),
        make_source("rightmag", 2),
        make_source("intlnews", None, country="GB", tier="intl"),
        make_source("intlnews2", None, country="QA", tier="intl"),
    ]
    return {s.id: s for s in sources}


def art(source_id: str, title: str, *, minutes_ago=30, summary="", author="", url=None) -> Article:
    return Article(
        source_id=source_id,
        title=title,
        url=url or f"https://{source_id}.example/{abs(hash(title)) % 10**8}",
        published_at=NOW - timedelta(minutes=minutes_ago),
        summary=summary,
        author=author,
    )
