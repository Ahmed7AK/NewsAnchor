"""Scoring stories for balanced exposure and source diversity.

Design position, stated plainly because it shapes every number below:

  NewsAnchor does not claim to remove bias. It cannot. What it can do is make
  the shape of the coverage visible -- who covered a story, from where, how
  many of them were actually independent, and which parts of the spectrum said
  nothing at all -- and then rank the feed so that stories you would otherwise
  only encounter from one direction rise instead of sink.

Four numbers per story:

  balance_score    how evenly the story was covered across the left-right axis
  diversity_score  how many genuinely independent newsrooms, and how varied
  prominence       how much attention it got overall
  rank_score       what actually orders your feed, combining the three

The important design choice is that balance and diversity *multiply into* the
rank rather than merely being displayed. A ranking driven by prominence alone
reproduces whatever the loudest cluster of outlets decided mattered -- which is
the problem the app exists to solve.
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import UTC, datetime

from .models import LEAN_ORDER, Article, Source, Story
from .wires import independent_newsrooms

# Half-life for prominence decay. 18h means yesterday evening's big story is
# still visible this morning at roughly half weight, which matches how a daily
# digest is actually read.
RECENCY_HALFLIFE_HOURS = 18.0


def _independent_articles(story: Story) -> list[Article]:
    """One article per independent newsroom.

    Forty outlets reprinting one AP wire story is one newsroom's account. We
    keep the first-published instance of each and drop the reprints, so that
    every count downstream reflects independent reporting.
    """
    best: dict[str, Article] = {}
    for article in sorted(story.articles, key=lambda a: a.published_at):
        room = article.syndicated_from or article.source_id
        best.setdefault(room, article)
    return list(best.values())


def lean_histogram(story: Story, registry: dict[str, Source]) -> tuple[dict[int, int], int]:
    """Count independent newsrooms at each point on the axis.

    Returns (histogram, unrated_count). Unrated is not a bucket on the axis --
    it is mostly international outlets, which are counted toward diversity
    instead. Folding them into "center" would be a lie.
    """
    hist = dict.fromkeys(LEAN_ORDER, 0)
    unrated = 0
    for article in _independent_articles(story):
        # Attribute to the newsroom that did the reporting, not the outlet that
        # reprinted it. A left-leaning paper carrying an AP dispatch has not
        # produced left-leaning coverage -- it has reprinted the wire, and
        # counting it as the former is precisely the distortion this module
        # exists to prevent.
        newsroom_id = article.syndicated_from or article.source_id
        source = registry.get(newsroom_id)
        if source is None or source.lean is None:
            unrated += 1
            continue
        hist[source.lean] += 1
    return hist, unrated


def balance_score(hist: dict[int, int], pollable: set[int]) -> float:
    """0..1 -- how evenly a story is covered across the spectrum.

    Normalised Shannon entropy over the buckets we can actually observe.
    1.0 means every part of the spectrum we poll covered it about equally;
    0.0 means it came from exactly one direction.

    `pollable` is the set of lean values for which we have at least one active
    source. Scoring against buckets we never poll would permanently cap every
    story below 1.0 and make the number meaningless.
    """
    counts = [hist.get(lean, 0) for lean in sorted(pollable)]
    total = sum(counts)
    if total == 0 or len(counts) <= 1:
        return 0.0

    entropy = 0.0
    for count in counts:
        if count:
            p = count / total
            entropy -= p * math.log(p)
    # Floating point puts a perfectly even split marginally above 1.0; the
    # score is documented as 0..1 and callers rely on that.
    return min(entropy / math.log(len(counts)), 1.0)


def coverage_gaps(hist: dict[int, int], pollable: set[int]) -> list[int]:
    """Spectrum positions that we poll but that published nothing on this story.

    Only meaningful once a story has some traction -- a gap on a story only one
    outlet ran is not a blind spot, it is just a small story.
    """
    return sorted(lean for lean in pollable if hist.get(lean, 0) == 0)


def diversity_score(story: Story, registry: dict[str, Source]) -> float:
    """0..1 -- breadth of genuinely distinct perspectives.

    Three components, because "many sources" can mean three different things
    and only one of them is worth much:
      newsroom  independent newsrooms, wire reprints collapsed
      country   how many countries reported it
      original  what fraction of the coverage was original vs reprinted wire
    """
    rooms = independent_newsrooms(story.articles)
    if not rooms:
        return 0.0

    # Saturating at 6 independent newsrooms: the difference between 1 and 4 is
    # large, between 12 and 15 is noise.
    newsroom = min(len(rooms), 6) / 6.0

    countries = {registry[a.source_id].country for a in story.articles if a.source_id in registry}
    country = min(len(countries), 4) / 4.0

    reprinted = sum(1 for a in story.articles if a.syndicated_from)
    original = 1.0 - (reprinted / len(story.articles))

    return round(0.5 * newsroom + 0.3 * country + 0.2 * original, 4)


def prominence(story: Story, now: datetime | None = None) -> float:
    """0..1 -- how much attention the story got, decayed by age."""
    now = now or datetime.now(UTC)
    volume = min(len(story.articles), 12) / 12.0

    age_hours = max((now - story.newest).total_seconds() / 3600.0, 0.0)
    recency = 0.5 ** (age_hours / RECENCY_HALFLIFE_HOURS)

    return round(0.6 * volume + 0.4 * recency, 4)


def score_story(
    story: Story,
    registry: dict[str, Source],
    pollable: set[int],
    *,
    now: datetime | None = None,
    balance_weight: float = 0.35,
    diversity_weight: float = 0.25,
) -> Story:
    hist, unrated = lean_histogram(story, registry)
    story.lean_histogram = hist
    story.unrated_newsrooms = unrated
    story.balance_score = round(balance_score(hist, pollable), 4)
    story.diversity_score = diversity_score(story, registry)
    story.prominence = prominence(story, now)

    # A gap is only meaningful once enough *rated* newsrooms have weighed in
    # to make silence elsewhere informative. Two guards:
    #   - fewer than two rated newsrooms and we would be crying "blind spot"
    #     over an ordinary small story;
    #   - a story carried only by unrated outlets (typically international)
    #     has an empty histogram, and reporting all five positions as silent
    #     says nothing about the story and everything about our roster.
    story.coverage_gaps = coverage_gaps(hist, pollable) if sum(hist.values()) >= 2 else []

    prominence_weight = 1.0 - balance_weight - diversity_weight
    story.rank_score = round(
        prominence_weight * story.prominence
        + balance_weight * story.balance_score
        + diversity_weight * story.diversity_score,
        4,
    )
    return story


def enforce_source_diversity(stories: list[Story], *, max_share: float = 0.30) -> list[Story]:
    """Reorder so no single newsroom dominates the top of the feed.

    Without this, an outlet that simply publishes more than the others ends up
    owning your morning -- which is source concentration wearing the costume of
    relevance. We walk the ranked list and defer any story whose lead newsroom
    already holds `max_share` of the slots placed so far.

    Nothing is dropped; heavy publishers are pushed down, not out.
    """
    if not stories:
        return []

    ordered = sorted(stories, key=lambda s: s.rank_score, reverse=True)
    placed: list[Story] = []
    deferred: list[Story] = []
    counts: Counter[str] = Counter()

    for story in ordered:
        lead = min(story.articles, key=lambda a: a.published_at)
        room = lead.syndicated_from or lead.source_id

        # Always allow the first few, otherwise the cap is meaningless at n=1.
        cap = max(2, int(max_share * (len(placed) + 1)))
        if counts[room] >= cap:
            deferred.append(story)
            continue

        placed.append(story)
        counts[room] += 1

    return placed + deferred


def pollable_leans(sources: list[Source]) -> set[int]:
    """Spectrum positions we have at least one active source for."""
    return {s.lean for s in sources if s.lean is not None}


def roster_warnings(sources: list[Source]) -> list[str]:
    """Flag imbalance in the source roster itself.

    A feed cannot be balanced if the inputs are not. This is checked and
    reported rather than silently absorbed, because an under-represented side
    of the roster looks identical to a genuine coverage gap in the output.
    """
    warnings: list[str] = []
    by_lean = Counter(s.lean for s in sources if s.lean is not None)

    missing = [lean for lean in LEAN_ORDER if by_lean.get(lean, 0) == 0]
    if missing:
        warnings.append(
            "no active sources at lean "
            + ", ".join(f"{lean:+d}" for lean in missing)
            + " -- coverage gaps there will be reported but are unverifiable"
        )

    present = [c for c in by_lean.values() if c]
    if present and max(present) >= 3 * min(present):
        detail = ", ".join(f"{lean:+d}:{by_lean.get(lean, 0)}" for lean in LEAN_ORDER)
        warnings.append(
            f"source roster is lopsided ({detail}); stories will skew toward the "
            "over-represented side regardless of scoring"
        )
    return warnings
