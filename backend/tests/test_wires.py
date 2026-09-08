from __future__ import annotations

from conftest import art

from newsanchor.wires import annotate, detect_wire, independent_newsrooms


def test_detects_common_wire_credits():
    assert detect_wire(art("leftpaper", "T", author="By J. DOE, Associated Press")) == "ap"
    assert detect_wire(art("leftpaper", "T", summary="(Reuters) - Talks resumed")) == "reuters"
    assert detect_wire(art("leftpaper", "T", author="AFP")) == "afp"
    assert detect_wire(art("leftpaper", "T", author="PA Media")) == "pa"


def test_staff_bylines_are_not_wire():
    assert detect_wire(art("leftpaper", "T", author="By Staff Writer")) is None
    assert detect_wire(art("leftpaper", "T", summary="A normal summary.")) is None


def test_body_mentions_do_not_trigger_false_positives():
    """An article that merely mentions a wire is not syndicated from it.
    A false positive here would erase a newsroom's own reporting."""
    article = art(
        "leftpaper",
        "Analysis of wire coverage",
        summary=(
            "A long piece about the news industry. " * 8
            + "It discusses how Reuters and the Associated Press operate."
        ),
    )
    assert detect_wire(article) is None


def test_outlet_publishing_its_own_wire_copy_is_not_syndication():
    article = art("ap", "AP story", author="By J. DOE, Associated Press")
    annotate([article])
    assert article.syndicated_from is None


def test_independent_newsrooms_collapses_reprints():
    wire = "By J. DOE, Associated Press"
    articles = [
        art("leftpaper", "Same story", author=wire),
        art("rightmag", "Same story", author=wire),
        art("intlnews", "Same story", author=wire),
        art("leftmag", "Original reporting", author="Staff"),
    ]
    annotate(articles)
    assert independent_newsrooms(articles) == {"ap", "leftmag"}
