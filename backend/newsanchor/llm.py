"""Optional neutral-summary generation.

Everything else in NewsAnchor works with no API key and no model. This module
is the one place an LLM is used, and it is off unless ANTHROPIC_API_KEY is set.

The prompt is deliberately narrow. Asking a model to "remove bias" invites it
to substitute its own judgement about what is true, which is a worse problem
than the one being solved. Instead it is asked to do something checkable:
report only what the supplied articles agree on, and say plainly where they
disagree. Disagreement between outlets is signal for the reader, not noise to
be smoothed away.
"""

from __future__ import annotations

import os

from .models import Source, Story

MODEL = os.environ.get("NEWSANCHOR_MODEL", "claude-sonnet-5")

SYSTEM = """You summarise news for a reader who wants to know what happened \
without being nudged toward a conclusion.

You will be given several outlets' coverage of one story. Write 2-4 sentences.

Rules:
- Report only facts that appear in the supplied coverage. Add nothing from
  your own knowledge, and do not speculate about causes or consequences.
- Where outlets agree on a fact, state it plainly.
- Where they disagree or emphasise different things, say so explicitly and
  attribute it ("X reports ..., while Y frames it as ..."). Do not average
  conflicting accounts into a single confident claim.
- Strip loaded and evaluative language. Prefer the plainer word.
- Attribute contested claims to whoever made them rather than asserting them.
- No opinion, no recommendation, no editorialising about the coverage itself.
- If the coverage is too thin to summarise responsibly, say exactly that."""


def _build_prompt(story: Story, registry: dict[str, Source]) -> str:
    lines = ["Coverage of one story from multiple outlets:\n"]
    for article in sorted(story.articles, key=lambda a: a.published_at):
        source = registry.get(article.source_id)
        name = source.name if source else article.source_id
        origin = f" [syndicated from {article.syndicated_from}]" if article.syndicated_from else ""
        lines.append(f"--- {name}{origin}")
        lines.append(f"Headline: {article.title}")
        if article.summary:
            lines.append(f"Summary: {article.summary}")
        lines.append("")
    return "\n".join(lines)


def is_available() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def summarise_story(story: Story, registry: dict[str, Source]) -> str:
    """Return a neutral summary, or '' if the LLM layer is unavailable.

    Failure is never fatal: a digest without summaries is still a digest.
    """
    if not is_available():
        return ""

    import anthropic

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=MODEL,
            max_tokens=400,
            system=SYSTEM,
            messages=[{"role": "user", "content": _build_prompt(story, registry)}],
        )
        return "".join(block.text for block in response.content if block.type == "text").strip()
    except Exception:  # noqa: BLE001 - see below
        # Intentionally broad. Summaries are a bonus feature; a rate limit,
        # a network blip or an SDK change must degrade the digest to "no
        # summaries", never fail the run that already fetched everything.
        return ""


def summarise_digest(stories: list[Story], registry: dict[str, Source], limit: int = 10) -> None:
    """Summarise the top `limit` stories in place.

    Capped because this is the only part of a run that costs money, and the
    marginal value of a neutral summary on story #37 is close to zero.
    """
    if not is_available():
        return
    for story in stories[:limit]:
        if len(story.articles) >= 2:
            story.neutral_summary = summarise_story(story, registry)
