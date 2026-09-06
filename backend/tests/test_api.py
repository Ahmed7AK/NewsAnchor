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
    assert abs(shares["leftpaper"] - 0.375) < 1e-6
    assert sum(body["by_lean"].values()) == 8
