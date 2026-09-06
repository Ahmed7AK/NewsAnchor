"""End-to-end: articles in, ranked digest out, stored and reloaded."""

from __future__ import annotations

from datetime import timedelta

from conftest import NOW, art

from newsanchor import db
from newsanchor.digest import DigestOptions, build_digest


def sample_articles():
    wire = "By J. DOE, Associated Press"
    return [
        # A story covered right across the spectrum.
        art(
            "leftpaper",
            "Senate passes spending bill in late-night vote",
            summary="The Senate voted 63-36 to approve the spending package.",
            minutes_ago=60,
        ),
        art(
            "rightmag",
            "Congress averts shutdown as Senate clears spending package",
            summary="Lawmakers approved the spending measure before funding lapsed.",
            minutes_ago=55,
        ),
        art(
            "centerwire",
            "Senate approves spending bill, ending standoff",
            summary="The Senate approved the spending package after weeks of talks.",
            minutes_ago=50,
        ),
        # A louder story, but only one side ran it.
        art(
            "leftpaper",
            "Report finds gaps in federal housing programme",
            summary="A new report describes shortfalls in the federal housing programme.",
            minutes_ago=40,
        ),
        art(
            "leftmag",
            "Federal housing programme criticised in new report",
            summary="The report describes shortfalls in the federal housing programme.",
            minutes_ago=35,
        ),
        # Wire copy reprinted by three outlets: one newsroom, not three.
        art(
            "leftpaper",
            "Cyclone makes landfall in Queensland",
            summary="The cyclone came ashore overnight bringing heavy rain.",
            author=wire,
            minutes_ago=30,
        ),
        art(
            "rightpaper",
            "Cyclone makes landfall in Queensland",
            summary="The cyclone came ashore overnight bringing heavy rain.",
            author=wire,
            minutes_ago=28,
        ),
        art(
            "rightmag",
            "Cyclone makes landfall in Queensland",
            summary="The cyclone came ashore overnight bringing heavy rain.",
            author=wire,
            minutes_ago=26,
        ),
    ]


def test_pipeline_produces_scored_ordered_stories(registry):
    sources = list(registry.values())
    digest = build_digest(sample_articles(), sources, registry, DigestOptions(), now=NOW)

    assert digest.article_count == 8
    assert digest.stories
    # Scores must be ordered and in range.
    assert all(0.0 <= s.rank_score <= 1.0 for s in digest.stories)

    titles = [s.articles[0].title for s in digest.stories]
    assert any("Senate" in t for t in titles)
    assert any("Cyclone" in t for t in titles)


def test_wire_reprints_collapse_to_one_newsroom(registry):
    sources = list(registry.values())
    digest = build_digest(sample_articles(), sources, registry, DigestOptions(), now=NOW)

    cyclone = next(s for s in digest.stories if "Cyclone" in s.articles[0].title)
    assert len(cyclone.articles) == 3, "three outlets carried it"
    # ...but they are all the same AP dispatch, so the spectrum shows one entry
    # (unrated, because 'ap' is not in the test registry) rather than three.
    assert sum(cyclone.lean_histogram.values()) == 0
    assert cyclone.diversity_score < 0.5, "reprints must not read as diverse coverage"


def test_balanced_story_outranks_a_one_sided_one(registry):
    sources = list(registry.values())
    digest = build_digest(sample_articles(), sources, registry, DigestOptions(), now=NOW)

    senate = next(s for s in digest.stories if "Senate" in s.articles[0].title)
    housing = next(s for s in digest.stories if "housing" in s.articles[0].title.lower())
    assert senate.balance_score > housing.balance_score
    assert senate.rank_score > housing.rank_score


def test_coverage_gaps_name_the_silent_side(registry):
    sources = list(registry.values())
    digest = build_digest(sample_articles(), sources, registry, DigestOptions(), now=NOW)
    housing = next(s for s in digest.stories if "housing" in s.articles[0].title.lower())
    # Covered only by leftpaper (-1) and leftmag (-2).
    assert set(housing.coverage_gaps) == {0, 1, 2}


def test_digest_survives_a_roundtrip_through_sqlite(tmp_path, registry):
    sources = list(registry.values())
    digest = build_digest(sample_articles(), sources, registry, DigestOptions(), now=NOW)
    path = tmp_path / "test.db"

    with db.connect(path) as conn:
        digest_id = db.save_digest(conn, digest)
    with db.connect(path) as conn:
        loaded = db.load_digest(conn, digest_id)

    assert loaded is not None
    assert len(loaded.stories) == len(digest.stories)
    assert [s.id for s in loaded.stories] == [s.id for s in digest.stories]
    assert [round(s.rank_score, 4) for s in loaded.stories] == [
        round(s.rank_score, 4) for s in digest.stories
    ]
    original = {a.url for s in digest.stories for a in s.articles}
    restored = {a.url for s in loaded.stories for a in s.articles}
    assert original == restored


def test_saving_twice_is_idempotent_for_articles(tmp_path, registry):
    """Re-running a digest must not duplicate article rows."""
    sources = list(registry.values())
    digest = build_digest(sample_articles(), sources, registry, DigestOptions(), now=NOW)
    path = tmp_path / "test.db"

    with db.connect(path) as conn:
        db.save_digest(conn, digest)
        db.save_digest(conn, digest)
        count = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    assert count == 8


def test_reading_balance_reports_share_per_outlet(tmp_path, registry):
    sources = list(registry.values())
    digest = build_digest(sample_articles(), sources, registry, DigestOptions(), now=NOW)
    path = tmp_path / "test.db"

    with db.connect(path) as conn:
        db.save_digest(conn, digest)
        counts = db.reading_balance(conn, days=30)

    assert counts["leftpaper"] == 3
    assert sum(counts.values()) == 8


def test_empty_input_yields_empty_digest(registry):
    digest = build_digest([], list(registry.values()), registry, DigestOptions(), now=NOW)
    assert digest.stories == []
    assert digest.article_count == 0


def test_window_start_reflects_options(registry):
    options = DigestOptions(window_hours=6)
    digest = build_digest([], list(registry.values()), registry, options, now=NOW)
    assert digest.window_start == NOW - timedelta(hours=6)
