from __future__ import annotations

from datetime import timedelta

import pytest
from conftest import NOW, make_source
from fixtures.make_feed import rss

from newsanchor.ingest.gdelt import GDELTAdapter
from newsanchor.ingest.newsapi import NewsAPIAdapter
from newsanchor.ingest.rss import entries_to_articles

SOURCE = make_source("leftpaper", -1)
SINCE = NOW - timedelta(hours=24)


def test_parses_items_within_window():
    feed = rss(
        [
            {
                "title": "Senate passes bill",
                "link": "https://x.example/1",
                "summary": "<p>The Senate <b>voted</b> 63-36.</p>",
                "published": NOW - timedelta(hours=2),
            },
            {
                "title": "Older story",
                "link": "https://x.example/2",
                "published": NOW - timedelta(days=3),
            },
        ]
    )
    articles = entries_to_articles(SOURCE, feed, SINCE)
    assert [a.title for a in articles] == ["Senate passes bill"]
    assert articles[0].summary == "The Senate voted 63-36."
    assert articles[0].source_id == "leftpaper"


def test_html_entities_and_tags_are_stripped():
    feed = rss(
        [
            {
                "title": "Tariffs &amp; trade",
                "link": "https://x.example/3",
                "summary": "<div>Talks &quot;stalled&quot;</div>",
                "published": NOW - timedelta(hours=1),
            }
        ]
    )
    article = entries_to_articles(SOURCE, feed, SINCE)[0]
    assert article.title == "Tariffs & trade"
    assert article.summary == 'Talks "stalled"'


def test_undated_entries_are_skipped():
    """Undated feed items are usually evergreen boilerplate. Assuming 'now'
    would let them squat at the top of every digest forever."""
    feed = rss([{"title": "No date here", "link": "https://x.example/4"}])
    assert entries_to_articles(SOURCE, feed, SINCE) == []


def test_entries_missing_title_or_link_are_skipped():
    feed = rss(
        [
            {"title": "", "link": "https://x.example/5", "published": NOW},
            {"title": "No link", "link": "", "published": NOW},
        ]
    )
    assert entries_to_articles(SOURCE, feed, SINCE) == []


def test_malformed_feed_does_not_raise():
    assert entries_to_articles(SOURCE, b"<not xml at all", SINCE) == []
    assert entries_to_articles(SOURCE, b"", SINCE) == []


def test_article_identity_is_url_based():
    """Outlets rewrite headlines in place; the URL is what stays put."""
    published = NOW - timedelta(hours=1)
    first = entries_to_articles(
        SOURCE,
        rss(
            [
                {
                    "title": "Breaking: something",
                    "link": "https://x.example/9",
                    "published": published,
                }
            ]
        ),
        SINCE,
    )[0]
    second = entries_to_articles(
        SOURCE,
        rss(
            [
                {
                    "title": "Updated headline entirely",
                    "link": "https://x.example/9",
                    "published": published,
                }
            ]
        ),
        SINCE,
    )[0]
    assert first.id == second.id


def test_gdelt_parses_and_marks_provenance():
    payload = {
        "articles": [
            {
                "url": "https://somewhere.example/a",
                "title": "A story",
                "seendate": "20260906T110000Z",
                "domain": "somewhere.example",
            },
            {
                "url": "https://old.example/b",
                "title": "Too old",
                "seendate": "20260901T110000Z",
                "domain": "old.example",
            },
        ]
    }
    articles = GDELTAdapter("test").to_articles(payload, SINCE)
    assert len(articles) == 1
    # GDELT attribution is domain-level and unreliable, so it is namespaced and
    # never silently treated as a rated source.
    assert articles[0].source_id == "gdelt:somewhere.example"


def test_gdelt_tolerates_empty_payload():
    assert GDELTAdapter("test").to_articles({}, SINCE) == []


@pytest.mark.asyncio
async def test_newsapi_without_key_reports_rather_than_raises():
    adapter = NewsAPIAdapter(api_key="")
    result = await adapter.fetch(SINCE)
    assert result.articles == []
    assert any("NEWSAPI_KEY" in e for e in result.errors)


def test_newsapi_parses_iso_timestamps():
    payload = {
        "status": "ok",
        "articles": [
            {
                "url": "https://n.example/1",
                "title": "Headline",
                "publishedAt": "2026-09-06T11:00:00Z",
                "description": "Body",
            },
        ],
    }
    articles = NewsAPIAdapter(api_key="x").to_articles(payload, SINCE)
    assert len(articles) == 1 and articles[0].source_id == "newsapi:n.example"
