from __future__ import annotations

from fastapi.testclient import TestClient

from newsanchor.api import app

client = TestClient(app)


def test_health_reports_roster_size():
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["sources_configured"] > 20
    assert body["sources_active"] > 20


def test_sources_endpoint_exposes_lean_and_warnings():
    body = client.get("/api/sources").json()
    assert len(body["sources"]) > 20

    entry = next(s for s in body["sources"] if s["id"] == "foxnews")
    assert entry["lean"] == 2 and entry["lean_label"] == "right"

    # State-affiliated outlets must be present but flagged and off by default.
    tass = next(s for s in body["sources"] if s["id"] == "tass")
    assert tass["state_affiliated"] is True and tass["enabled"] is False

    assert set(body["spectrum"]) == {"left", "lean-left", "center", "lean-right", "right"}
    assert body["pollable_leans"] == [-2, -1, 0, 1, 2]


def test_digest_404s_before_any_refresh(tmp_path, monkeypatch):
    monkeypatch.setattr("newsanchor.db.DEFAULT_DB", tmp_path / "empty.db")
    response = client.get("/api/digest")
    assert response.status_code == 404
    assert "refresh" in response.json()["detail"]


def test_digest_serialises_a_stored_run(tmp_path, monkeypatch, registry):
    from conftest import NOW

    from newsanchor import db
    from newsanchor.digest import DigestOptions, build_digest
    from tests.test_pipeline import sample_articles

    path = tmp_path / "api.db"
    monkeypatch.setattr("newsanchor.db.DEFAULT_DB", path)
    monkeypatch.setattr("newsanchor.api.default_registry", lambda: registry)

    digest = build_digest(
        sample_articles(), list(registry.values()), registry, DigestOptions(), now=NOW
    )
    with db.connect(path) as conn:
        db.save_digest(conn, digest)

    body = client.get("/api/digest").json()
    assert body["article_count"] == 8
    assert body["stories"]

    story = body["stories"][0]
    for key in (
        "id",
        "headline",
        "by_lean",
        "lean_histogram",
        "coverage_gaps",
        "balance_score",
        "diversity_score",
        "source_count",
        "reprint_count",
    ):
        assert key in story

    # Histograms are exposed with human labels, not raw integers.
    assert set(story["lean_histogram"]) <= {"left", "lean-left", "center", "lean-right", "right"}


def test_refresh_rejects_absurd_windows():
    assert client.post("/api/refresh?window_hours=0").status_code == 422
    assert client.post("/api/refresh?window_hours=100000").status_code == 422


def test_reading_balance_reports_shares(tmp_path, monkeypatch, registry):
    from conftest import NOW

    from newsanchor import db
    from newsanchor.digest import DigestOptions, build_digest
    from tests.test_pipeline import sample_articles

    path = tmp_path / "balance.db"
    monkeypatch.setattr("newsanchor.db.DEFAULT_DB", path)
    monkeypatch.setattr("newsanchor.api.default_registry", lambda: registry)

    digest = build_digest(
        sample_articles(), list(registry.values()), registry, DigestOptions(), now=NOW
    )
    with db.connect(path) as conn:
        db.save_digest(conn, digest)

    body = client.get("/api/reading-balance").json()
    assert body["total_articles"] == 8
    shares = {row["id"]: row["share"] for row in body["by_source"]}
    # 2 of 8, not 3: leftpaper's AP reprint is attributed to the wire.
    assert abs(shares["leftpaper"] - 0.25) < 1e-6
    assert abs(shares["ap"] - 0.375) < 1e-6
    assert sum(body["by_lean"].values()) == 8


def _seed(tmp_path, monkeypatch, registry, name="wire.db"):
    from conftest import NOW

    from newsanchor import db
    from newsanchor.digest import DigestOptions, build_digest
    from tests.test_pipeline import sample_articles

    path = tmp_path / name
    monkeypatch.setattr("newsanchor.db.DEFAULT_DB", path)
    monkeypatch.setattr("newsanchor.api.default_registry", lambda: registry)
    digest = build_digest(
        sample_articles(), list(registry.values()), registry, DigestOptions(), now=NOW
    )
    with db.connect(path) as conn:
        db.save_digest(conn, digest)
    return path


def test_by_lean_never_contradicts_the_histogram(tmp_path, monkeypatch, registry):
    """Regression: the coverage list used to group by the reprinting outlet.

    A single AP dispatch carried by a left-leaning and a right-leaning paper
    appeared under both positions, so the story read as cross-spectrum when it
    was one wire report -- directly contradicting the histogram shown above it.
    """
    _seed(tmp_path, monkeypatch, registry)
    body = client.get("/api/digest").json()

    cyclone = next(s for s in body["stories"] if "Cyclone" in s["headline"])

    # Three outlets carried it, but they are one AP dispatch.
    assert cyclone["reprint_count"] == 3
    assert sum(len(v) for v in cyclone["by_lean"].values()) == 1, (
        "three reprints of one wire story must collapse to a single entry"
    )

    # Every position named in by_lean must be backed by the histogram (or be
    # the unrated bucket), never invented by the carrier's lean.
    for label, items in cyclone["by_lean"].items():
        if label == "unrated":
            assert cyclone["unrated_newsrooms"] >= len(items)
        else:
            assert cyclone["lean_histogram"].get(label, 0) >= len(items), (
                f"by_lean claims {label} coverage the histogram does not show"
            )


def test_coverage_entries_report_the_newsroom_not_the_carrier(tmp_path, monkeypatch, registry):
    _seed(tmp_path, monkeypatch, registry, name="newsroom.db")
    body = client.get("/api/digest").json()
    cyclone = next(s for s in body["stories"] if "Cyclone" in s["headline"])

    entry = next(iter(cyclone["by_lean"].values()))[0]
    assert entry["newsroom"]["id"] == "ap", "must attribute to the wire, not the reprinter"
    assert entry["carried_by"] == 3, "UI needs the reprint count to say 'reprinted by 3'"


def test_unrated_coverage_is_visible_rather_than_silently_dropped(tmp_path, monkeypatch, registry):
    """A story carried only by international outlets used to render as a row of
    empty spectrum cells -- indistinguishable from no coverage at all."""
    from conftest import NOW, art

    from newsanchor import db
    from newsanchor.digest import DigestOptions, build_digest

    path = tmp_path / "intl.db"
    monkeypatch.setattr("newsanchor.db.DEFAULT_DB", path)
    monkeypatch.setattr("newsanchor.api.default_registry", lambda: registry)

    articles = [
        art(
            "intlnews",
            "Earthquake strikes off Japan",
            summary="A quake struck off Honshu, no tsunami warning issued.",
        ),
        art(
            "intlnews2",
            "Quake hits waters near Japan",
            summary="A tremor was recorded off the Honshu coast, no warning issued.",
        ),
    ]
    digest = build_digest(articles, list(registry.values()), registry, DigestOptions(), now=NOW)
    with db.connect(path) as conn:
        db.save_digest(conn, digest)

    story = client.get("/api/digest").json()["stories"][0]
    assert sum(story["lean_histogram"].values()) == 0
    assert story["unrated_newsrooms"] == 2, (
        "international coverage must be counted somewhere the UI can show it"
    )


def test_unrated_count_survives_the_database_roundtrip(tmp_path, monkeypatch, registry):
    _seed(tmp_path, monkeypatch, registry, name="roundtrip.db")
    body = client.get("/api/digest").json()
    assert all("unrated_newsrooms" in s for s in body["stories"])
