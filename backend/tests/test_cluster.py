from __future__ import annotations

import numpy as np
import pytest
from conftest import art
from sklearn.metrics import adjusted_rand_score

from newsanchor.cluster import DEFAULT_DISTANCE_THRESHOLD, cluster_articles, normalise
from tests.gold import GOLD, gold_articles


def test_normalise_strips_outlet_suffix_and_furniture():
    assert normalise("Senate passes bill - BBC News") == "senate passes bill"
    assert "live updates" not in normalise("LIVE UPDATES: Senate passes bill")
    assert normalise("Report: Talks stall | Reuters") == "report talks stall"


def test_same_event_different_outlets_clusters_together():
    shared = "The Senate voted 63-36 to approve the spending package, averting a shutdown."
    articles = [
        art("leftpaper", "Senate passes spending bill in late-night vote", summary=shared),
        art("rightmag", "Congress averts shutdown as Senate clears spending package",
            summary="Lawmakers approved the spending measure hours before funding lapsed."),
        art("intlnews", "US Senate approves spending bill, ending shutdown standoff",
            summary="The vote ends weeks of brinkmanship over federal spending levels."),
    ]
    stories = cluster_articles(articles)
    assert len(stories) == 1
    assert stories[0].source_ids == {"leftpaper", "rightmag", "intlnews"}


def test_distinct_events_stay_separate():
    articles = [
        art("leftpaper", "Senate passes spending bill in late-night vote",
            summary="The Senate voted 63-36 to approve the spending package."),
        art("rightmag", "Congress averts shutdown as Senate clears spending package",
            summary="Lawmakers approved the spending measure before funding lapsed."),
        art("intlnews", "Magnitude 6.1 earthquake strikes off coast of Japan",
            summary="The quake struck at a depth of 40km off Honshu. No tsunami warning."),
        art("intlnews2", "Earthquake of magnitude 6.1 hits waters near Japan",
            summary="Japan's meteorological agency recorded the tremor off Honshu."),
    ]
    stories = cluster_articles(articles)
    assert len(stories) == 2
    grouped = sorted(sorted(s.source_ids) for s in stories)
    assert grouped == [["intlnews", "intlnews2"], ["leftpaper", "rightmag"]]


def test_single_article_and_empty_input():
    assert cluster_articles([]) == []
    stories = cluster_articles([art("leftpaper", "A lone headline about tariffs")])
    assert len(stories) == 1


def test_headline_that_normalises_to_nothing_does_not_crash():
    # Pure furniture -> empty vector. Must survive rather than poison the linkage
    # with NaN cosine distances.
    articles = [
        art("leftpaper", "Live updates"),
        art("rightmag", "Senate passes spending bill in late-night vote",
            summary="The Senate voted 63-36 to approve the package."),
        art("intlnews", "US Senate approves spending bill after standoff",
            summary="The Senate approved the spending package after weeks of talks."),
    ]
    stories = cluster_articles(articles)
    assert sum(len(s.articles) for s in stories) == 3


def test_no_article_is_lost_or_duplicated():
    articles, _ = gold_articles()
    stories = cluster_articles(articles)
    urls = [a.url for s in stories for a in s.articles]
    assert sorted(urls) == sorted(a.url for a in articles)


def test_story_ids_are_stable_across_input_order():
    articles = [
        art("leftpaper", "Senate passes spending bill in late-night vote",
            summary="The Senate voted 63-36 to approve the spending package."),
        art("rightmag", "Congress averts shutdown as Senate clears spending package",
            summary="Lawmakers approved the spending measure before funding lapsed."),
    ]
    first = cluster_articles(articles)
    second = cluster_articles(list(reversed(articles)))
    assert {s.id for s in first} == {s.id for s in second}


def test_min_sources_filters_single_outlet_stories():
    articles, _ = gold_articles()
    corroborated = cluster_articles(articles, min_sources=2)
    assert corroborated, "gold set contains multi-source stories"
    assert all(len(s.source_ids) >= 2 for s in corroborated)


def test_clustering_quality_does_not_regress():
    """Pins the benchmark number so a refactor cannot silently degrade clustering.

    See tests/benchmark_cluster.py for the full threshold sweep. 0.90 is a floor
    beneath the measured 0.926, not a target -- if this fails, run the benchmark
    and find out what changed rather than lowering the bound.
    """
    articles, truth = gold_articles()
    stories = cluster_articles(articles, distance_threshold=DEFAULT_DISTANCE_THRESHOLD)

    labels = {a.url: i for i, s in enumerate(stories) for a in s.articles}
    predicted = np.array([labels[a.url] for a in articles])

    ari = adjusted_rand_score(np.array(truth), predicted)
    assert ari >= 0.90, f"clustering quality regressed: ARI={ari:.3f} (expected >= 0.90)"


def test_near_miss_pairs_are_not_merged():
    """The cases this clusterer is most likely to get wrong, pinned explicitly."""
    articles, _ = gold_articles()
    stories = cluster_articles(articles)
    story_of = {a.url: s.id for s in stories for a in s.articles}

    def url_for(title_fragment: str) -> str:
        for a in articles:
            if title_fragment.lower() in a.title.lower():
                return a.url
        raise AssertionError(f"no gold article matching {title_fragment!r}")

    never_together = [
        ("Magnitude 6.1 earthquake strikes", "Magnitude 7.2 earthquake devastates"),
        ("Senate passes spending bill", "Senate rejects amendment"),
        ("Fed holds interest rates steady", "Fed governor resigns"),
    ]
    for left, right in never_together:
        assert story_of[url_for(left)] != story_of[url_for(right)], (
            f"wrongly merged: {left!r} with {right!r}"
        )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Known TF-IDF limitation. 'Supreme Court declines to hear gun rights appeal' "
        "merges into the tariff-case story: after stopword removal the two share "
        "court/justices/hear/case/authority, and bag-of-words has no way to tell "
        "that 'tariff' and 'gun' name different disputes. This is the single error "
        "behind the benchmark's 0.926 rather than 1.0. Fixing it needs semantics, "
        "not tuning -- see the embeddings upgrade path in cluster.py. Marked strict "
        "so that if a future change does fix it, this test fails loudly and gets "
        "promoted into test_near_miss_pairs_are_not_merged above."
    ),
)
def test_same_institution_different_case_is_not_merged():
    articles, _ = gold_articles()
    stories = cluster_articles(articles)
    story_of = {a.url: s.id for s in stories for a in s.articles}

    def url_for(fragment: str) -> str:
        return next(a.url for a in articles if fragment.lower() in a.title.lower())

    assert (
        story_of[url_for("Supreme Court agrees to hear major tariff")]
        != story_of[url_for("Supreme Court declines to hear gun")]
    )
