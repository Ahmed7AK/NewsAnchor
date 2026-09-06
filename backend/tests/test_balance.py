from __future__ import annotations

from conftest import NOW, art

from newsanchor.balance import (
    balance_score,
    coverage_gaps,
    diversity_score,
    enforce_source_diversity,
    lean_histogram,
    pollable_leans,
    roster_warnings,
    score_story,
)
from newsanchor.cluster import cluster_articles
from newsanchor.models import Story
from newsanchor.wires import annotate

POLLABLE = {-2, -1, 0, 1, 2}


def story_of(*articles) -> Story:
    annotate(list(articles))
    return Story(id="s", articles=list(articles))


def test_balance_score_is_one_when_evenly_spread():
    hist = {-2: 1, -1: 1, 0: 1, 1: 1, 2: 1}
    assert balance_score(hist, POLLABLE) == 1.0


def test_balance_score_is_zero_when_one_sided():
    hist = {-2: 3, -1: 2, 0: 0, 1: 0, 2: 0}
    assert balance_score(hist, POLLABLE) < 0.45
    assert balance_score({-2: 4, -1: 0, 0: 0, 1: 0, 2: 0}, POLLABLE) == 0.0


def test_balance_score_ignores_buckets_we_do_not_poll():
    """A gap we cannot observe must not permanently cap the score."""
    hist = {-2: 0, -1: 2, 0: 2, 1: 0, 2: 0}
    assert balance_score(hist, {-1, 0}) == 1.0
    assert balance_score(hist, POLLABLE) < 1.0


def test_coverage_gaps_lists_silent_side():
    hist = {-2: 2, -1: 1, 0: 1, 1: 0, 2: 0}
    assert coverage_gaps(hist, POLLABLE) == [1, 2]


def test_histogram_counts_newsrooms_not_reprints(registry):
    """Ten outlets running one AP story is one newsroom, not ten."""
    wire_credit = "By JANE DOE, Associated Press"
    story = story_of(
        art("leftpaper", "Storm hits coast", author=wire_credit),
        art("rightpaper", "Storm hits coast", author=wire_credit),
        art("rightmag", "Storm hits coast", author=wire_credit),
        art("leftmag", "Our own reporting on the storm", author="Staff Writer"),
    )
    hist, unrated = lean_histogram(story, registry)
    # three reprints collapse to the 'ap' newsroom, which is not in the test
    # registry and therefore counts as unrated -- not as three rated outlets.
    assert sum(hist.values()) == 1
    assert hist[-2] == 1
    assert unrated == 1


def test_diversity_rewards_countries_and_penalises_reprints(registry):
    wire = "By A. REPORTER, Associated Press"
    reprints = story_of(
        art("leftpaper", "Flood warning issued", author=wire),
        art("rightpaper", "Flood warning issued", author=wire),
        art("rightmag", "Flood warning issued", author=wire),
    )
    originals = story_of(
        art("leftpaper", "Flood warning issued", author="Staff"),
        art("intlnews", "Flood warning issued", author="Staff"),
        art("intlnews2", "Flood warning issued", author="Staff"),
    )
    assert diversity_score(originals, registry) > diversity_score(reprints, registry)


def test_score_story_populates_every_field(registry):
    story = story_of(
        art("leftpaper", "Senate passes spending bill",
            summary="The Senate approved the package."),
        art("rightmag", "Senate clears spending package",
            summary="Lawmakers approved the measure."),
    )
    score_story(story, registry, POLLABLE, now=NOW)
    assert 0.0 <= story.balance_score <= 1.0
    assert 0.0 <= story.diversity_score <= 1.0
    assert 0.0 <= story.prominence <= 1.0
    assert 0.0 <= story.rank_score <= 1.0
    assert story.lean_histogram[-1] == 1 and story.lean_histogram[2] == 1


def test_gaps_not_reported_for_single_newsroom_stories(registry):
    story = story_of(art("leftpaper", "A story only one outlet ran"))
    score_story(story, registry, POLLABLE, now=NOW)
    assert story.coverage_gaps == [], "a one-outlet item is small news, not a blind spot"


def test_balance_actually_changes_ranking(registry):
    """The point of the whole exercise: a balanced story should outrank a
    louder but one-sided one."""
    one_sided = story_of(*[
        art(sid, f"Left-only story {i}", summary="Only one side covered this.")
        for i, sid in enumerate(["leftpaper", "leftmag", "leftpaper", "leftmag"])
    ])
    balanced = story_of(
        art("leftpaper", "Balanced story", summary="Covered widely."),
        art("rightmag", "Balanced story", summary="Covered widely."),
        art("centerwire", "Balanced story", summary="Covered widely."),
    )
    for s in (one_sided, balanced):
        score_story(s, registry, POLLABLE, now=NOW)

    assert one_sided.prominence >= balanced.prominence, "one-sided story is the louder one"
    assert balanced.rank_score > one_sided.rank_score, (
        "balance weighting failed to lift the balanced story above the louder one"
    )


def test_enforce_source_diversity_defers_a_dominant_outlet():
    stories = []
    for i in range(10):
        # leftpaper leads 8 of 10 stories
        lead = "leftpaper" if i < 8 else "rightmag"
        s = Story(id=f"s{i}", articles=[art(lead, f"Story {i}")])
        s.rank_score = 1.0 - i * 0.01
        stories.append(s)

    ordered = enforce_source_diversity(stories, max_share=0.30)
    assert len(ordered) == 10, "nothing may be dropped, only reordered"

    lead_of = lambda s: s.articles[0].source_id  # noqa: E731
    top5 = [lead_of(s) for s in ordered[:5]]
    assert top5.count("leftpaper") <= 3, f"one outlet still dominates the top: {top5}"


def test_roster_warnings_flag_missing_and_lopsided(registry):
    balanced = [s for s in registry.values()]
    assert roster_warnings(balanced) == []

    from conftest import make_source

    lopsided = [make_source(f"l{i}", -1) for i in range(6)] + [make_source("r1", 1)]
    warnings = roster_warnings(lopsided)
    assert any("lopsided" in w for w in warnings)
    assert any("no active sources at lean" in w for w in warnings)


def test_pollable_leans_ignores_unrated(registry):
    assert pollable_leans(list(registry.values())) == {-2, -1, 0, 1, 2}
