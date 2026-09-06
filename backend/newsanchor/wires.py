"""Detecting syndicated wire copy.

This matters more than it looks. If AP files a story and forty outlets run it
verbatim, a naive aggregator reports "40 sources covered this, from across the
spectrum" -- which is the exact opposite of the truth. It is one newsroom's
account, reprinted. Counting it as broad corroboration is the single easiest
way for a balance-focused feed to mislead its reader.

So: detect it, collapse it, and report it honestly as "1 original report,
39 reprints".

Detection is heuristic and deliberately conservative. False negatives cost us
a little dedup quality; false positives would wrongly erase a newsroom's own
reporting, which is worse.
"""

from __future__ import annotations

import re

from .models import Article

# Credit lines as they actually appear in feed bylines and summary text.
WIRE_PATTERNS: dict[str, re.Pattern] = {
    "ap": re.compile(
        r"\b(?:the\s+)?associated\s+press\b|\(\s*AP\s*\)|\bAP\s+(?:News|Photo|writer)\b",
        re.IGNORECASE,
    ),
    "reuters": re.compile(r"\breuters\b|\(\s*Reuters\s*\)", re.IGNORECASE),
    "afp": re.compile(r"\bagence\s+france[- ]presse\b|\bAFP\b"),
    "pa": re.compile(r"\bpa\s+media\b|\bpress\s+association\b", re.IGNORECASE),
    "bloomberg": re.compile(r"\bbloomberg\s+news\b", re.IGNORECASE),
}


def detect_wire(article: Article) -> str | None:
    """Return the wire id this article appears to be syndicated from, if any.

    Only the byline and the opening of the summary are searched. Scanning the
    whole body would flag every article that merely *mentions* Reuters.
    """
    haystack = f"{article.author} || {article.summary[:200]}"
    for wire_id, pattern in WIRE_PATTERNS.items():
        if pattern.search(haystack):
            return wire_id
    return None


def annotate(articles: list[Article]) -> list[Article]:
    """Tag syndicated articles in place and return the same list."""
    for article in articles:
        # An outlet's own wire copy is not syndication -- AP publishing AP is
        # just AP. Only mark it when a *different* outlet is carrying it.
        wire_id = detect_wire(article)
        if wire_id and wire_id != article.source_id:
            article.syndicated_from = wire_id
    return articles


def independent_newsrooms(articles: list[Article]) -> set[str]:
    """Newsrooms that did their own reporting on a story.

    Every outlet running the same AP piece collapses to the single entry "ap".
    """
    rooms: set[str] = set()
    for article in articles:
        rooms.add(article.syndicated_from or article.source_id)
    return rooms
