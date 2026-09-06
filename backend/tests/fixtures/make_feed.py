"""Helper to synthesise RSS bytes for tests (no network required)."""

from __future__ import annotations

from email.utils import format_datetime
from xml.sax.saxutils import escape


def rss(items: list[dict], title: str = "Test Feed") -> bytes:
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0"><channel>',
        f"<title>{escape(title)}</title>",
    ]
    for item in items:
        parts.append("<item>")
        parts.append(f"<title>{escape(item['title'])}</title>")
        parts.append(f"<link>{escape(item['link'])}</link>")
        if "summary" in item:
            parts.append(f"<description>{escape(item['summary'])}</description>")
        if "author" in item:
            parts.append(f"<author>{escape(item['author'])}</author>")
        if "published" in item:
            parts.append(f"<pubDate>{format_datetime(item['published'])}</pubDate>")
        parts.append("</item>")
    parts.append("</channel></rss>")
    return "".join(parts).encode("utf-8")
