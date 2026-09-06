"""SQLite persistence.

Two jobs, both about history rather than caching:

  * Let you look at yesterday's digest without re-fetching (feeds only carry a
    rolling window, so a story you didn't read is otherwise gone).
  * Make it possible to ask questions across time -- which outlets you actually
    end up reading, whether the "blind spots" recur, whether your roster is as
    balanced in practice as it looks on paper.

Articles are keyed by URL hash so re-running a digest is idempotent.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .digest import Digest
from .models import Article, Story

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id            TEXT PRIMARY KEY,
    source_id     TEXT NOT NULL,
    title         TEXT NOT NULL,
    url           TEXT NOT NULL UNIQUE,
    summary       TEXT NOT NULL DEFAULT '',
    author        TEXT NOT NULL DEFAULT '',
    published_at  TEXT NOT NULL,
    syndicated_from TEXT,
    first_seen_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at);
CREATE INDEX IF NOT EXISTS idx_articles_source    ON articles(source_id);

CREATE TABLE IF NOT EXISTS digests (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at  TEXT NOT NULL,
    window_start  TEXT NOT NULL,
    article_count INTEGER NOT NULL,
    source_count  INTEGER NOT NULL,
    warnings      TEXT NOT NULL DEFAULT '[]',
    errors        TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS stories (
    id              TEXT NOT NULL,
    digest_id       INTEGER NOT NULL REFERENCES digests(id) ON DELETE CASCADE,
    lean_histogram  TEXT NOT NULL,
    coverage_gaps   TEXT NOT NULL,
    balance_score   REAL NOT NULL,
    diversity_score REAL NOT NULL,
    prominence      REAL NOT NULL,
    rank_score      REAL NOT NULL,
    neutral_summary TEXT NOT NULL DEFAULT '',
    position        INTEGER NOT NULL,
    PRIMARY KEY (id, digest_id)
);

CREATE TABLE IF NOT EXISTS story_articles (
    story_id   TEXT NOT NULL,
    digest_id  INTEGER NOT NULL,
    article_id TEXT NOT NULL REFERENCES articles(id),
    PRIMARY KEY (story_id, digest_id, article_id)
);
"""

DEFAULT_DB = Path.home() / ".newsanchor" / "newsanchor.db"


@contextmanager
def connect(path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    path = Path(path or DEFAULT_DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def save_digest(conn: sqlite3.Connection, digest: Digest) -> int:
    now = _iso(datetime.now(UTC))

    cursor = conn.execute(
        "INSERT INTO digests (generated_at, window_start, article_count, source_count,"
        " warnings, errors) VALUES (?,?,?,?,?,?)",
        (
            _iso(digest.generated_at),
            _iso(digest.window_start),
            digest.article_count,
            digest.source_count,
            json.dumps(digest.warnings),
            json.dumps(digest.errors),
        ),
    )
    digest_id = int(cursor.lastrowid)

    for position, story in enumerate(digest.stories):
        for article in story.articles:
            conn.execute(
                "INSERT INTO articles (id, source_id, title, url, summary, author,"
                " published_at, syndicated_from, first_seen_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(id) DO UPDATE SET title=excluded.title",
                (
                    article.id,
                    article.source_id,
                    article.title,
                    article.url,
                    article.summary,
                    article.author,
                    _iso(article.published_at),
                    article.syndicated_from,
                    now,
                ),
            )
            conn.execute(
                "INSERT OR IGNORE INTO story_articles (story_id, digest_id, article_id)"
                " VALUES (?,?,?)",
                (story.id, digest_id, article.id),
            )

        conn.execute(
            "INSERT INTO stories (id, digest_id, lean_histogram, coverage_gaps,"
            " balance_score, diversity_score, prominence, rank_score, neutral_summary,"
            " position) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                story.id,
                digest_id,
                json.dumps({str(k): v for k, v in story.lean_histogram.items()}),
                json.dumps(story.coverage_gaps),
                story.balance_score,
                story.diversity_score,
                story.prominence,
                story.rank_score,
                story.neutral_summary,
                position,
            ),
        )

    return digest_id


def _row_to_article(row: sqlite3.Row) -> Article:
    return Article(
        source_id=row["source_id"],
        title=row["title"],
        url=row["url"],
        published_at=datetime.fromisoformat(row["published_at"]),
        summary=row["summary"],
        author=row["author"],
        syndicated_from=row["syndicated_from"],
    )


def load_digest(conn: sqlite3.Connection, digest_id: int | None = None) -> Digest | None:
    """Load a stored digest; the most recent one when no id is given."""
    if digest_id is None:
        row = conn.execute("SELECT * FROM digests ORDER BY generated_at DESC LIMIT 1").fetchone()
    else:
        row = conn.execute("SELECT * FROM digests WHERE id = ?", (digest_id,)).fetchone()
    if row is None:
        return None

    digest = Digest(
        generated_at=datetime.fromisoformat(row["generated_at"]),
        window_start=datetime.fromisoformat(row["window_start"]),
        article_count=row["article_count"],
        source_count=row["source_count"],
        warnings=json.loads(row["warnings"]),
        errors=json.loads(row["errors"]),
    )
    did = row["id"]

    for srow in conn.execute(
        "SELECT * FROM stories WHERE digest_id = ? ORDER BY position", (did,)
    ).fetchall():
        articles = [
            _row_to_article(arow)
            for arow in conn.execute(
                "SELECT a.* FROM articles a"
                " JOIN story_articles sa ON sa.article_id = a.id"
                " WHERE sa.story_id = ? AND sa.digest_id = ?"
                " ORDER BY a.published_at",
                (srow["id"], did),
            ).fetchall()
        ]
        digest.stories.append(
            Story(
                id=srow["id"],
                articles=articles,
                lean_histogram={int(k): v for k, v in json.loads(srow["lean_histogram"]).items()},
                coverage_gaps=json.loads(srow["coverage_gaps"]),
                balance_score=srow["balance_score"],
                diversity_score=srow["diversity_score"],
                prominence=srow["prominence"],
                rank_score=srow["rank_score"],
                neutral_summary=srow["neutral_summary"],
            )
        )
    return digest


def reading_balance(conn: sqlite3.Connection, days: int = 30) -> dict[str, int]:
    """How many articles per source landed in your digests recently.

    The honest check on whether the app is doing its job: if this is 70% one
    outlet, the feed is not diverse no matter what the per-story scores say.
    """
    rows = conn.execute(
        "SELECT a.source_id, COUNT(*) AS n FROM articles a"
        " WHERE a.first_seen_at >= datetime('now', ?)"
        " GROUP BY a.source_id ORDER BY n DESC",
        (f"-{int(days)} days",),
    ).fetchall()
    return {row["source_id"]: row["n"] for row in rows}
