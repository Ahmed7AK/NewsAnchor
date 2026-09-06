"""Core data types.

Deliberately plain dataclasses rather than ORM models. The pipeline is a
sequence of pure-ish transformations (fetch -> normalise -> cluster -> score)
and keeping the types dumb makes each stage trivial to test in isolation.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Optional

# The five-point axis used throughout. Deliberately coarse: finer gradations
# imply a precision that source-level bias ratings do not have.
LEAN_LABELS = {
    -2: "left",
    -1: "lean-left",
    0: "center",
    1: "lean-right",
    2: "right",
}
LEAN_ORDER = [-2, -1, 0, 1, 2]


class Tier(str):
    WIRE = "wire"
    NATIONAL = "national"
    MAGAZINE = "magazine"
    NONPROFIT = "nonprofit"
    INTL = "intl"


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    homepage: str
    feeds: tuple[str, ...] = ()
    lean: Optional[int] = None
    tier: str = Tier.NATIONAL
    country: str = "US"
    paywall: Optional[str] = None
    state_affiliated: bool = False
    enabled: bool = True
    notes: str = ""

    @property
    def lean_label(self) -> str:
        return LEAN_LABELS.get(self.lean, "unrated") if self.lean is not None else "unrated"

    @property
    def is_wire(self) -> bool:
        return self.tier == Tier.WIRE


@dataclass
class Article:
    """One story as published by one outlet."""

    source_id: str
    title: str
    url: str
    published_at: datetime
    summary: str = ""
    author: str = ""
    # Populated only when full-text extraction is enabled.
    body: str = ""
    # Set when the article is detectably syndicated wire copy (see wires.py).
    syndicated_from: Optional[str] = None

    @property
    def id(self) -> str:
        """Stable identity. URL, not title -- outlets rewrite headlines in place."""
        return hashlib.sha1(self.url.encode("utf-8")).hexdigest()[:16]

    @property
    def text_for_matching(self) -> str:
        """What the clusterer actually compares.

        Title is repeated because headlines carry most of the topical signal in
        a short document, and the summary field is frequently boilerplate
        ("Read more at...") that would otherwise dominate the vector.
        """
        return f"{self.title} {self.title} {self.summary}".strip()


@dataclass
class Story:
    """A cluster of articles from different outlets about the same event."""

    id: str
    articles: list[Article] = field(default_factory=list)
    # Filled in by balance.py
    lean_histogram: dict[int, int] = field(default_factory=dict)
    coverage_gaps: list[int] = field(default_factory=list)
    balance_score: float = 0.0
    diversity_score: float = 0.0
    prominence: float = 0.0
    rank_score: float = 0.0
    # Optional, only when an LLM provider is configured.
    neutral_summary: str = ""

    @property
    def newest(self) -> datetime:
        return max(a.published_at for a in self.articles)

    @property
    def source_ids(self) -> set[str]:
        return {a.source_id for a in self.articles}
