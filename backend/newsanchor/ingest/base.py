"""Ingest adapter protocol.

Every source of articles -- RSS, GDELT, NewsAPI, the Guardian's API -- reduces
to the same thing: given a time window, hand back Articles tagged with the
source they came from. Keeping that interface narrow is what lets the rest of
the pipeline stay ignorant of where articles came from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from ..models import Article


@dataclass
class FetchResult:
    articles: list[Article] = field(default_factory=list)
    # Non-fatal problems: a dead feed should degrade the run, not end it.
    errors: list[str] = field(default_factory=list)

    def extend(self, other: FetchResult) -> None:
        self.articles.extend(other.articles)
        self.errors.extend(other.errors)


class Adapter(Protocol):
    name: str

    async def fetch(self, since: datetime) -> FetchResult: ...
