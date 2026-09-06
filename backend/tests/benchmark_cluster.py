"""Clustering quality benchmark.

Not a pass/fail test -- a measurement. Run it after touching cluster.py:

    python tests/benchmark_cluster.py

It sweeps the distance threshold against a hand-labelled set of 21 stories and
prints adjusted Rand index for each. The set is deliberately adversarial: it
contains same-topic-different-event pairs (two earthquakes, two Supreme Court
actions, two Senate votes, two Fed items) which are the cases a bag-of-words
clusterer gets wrong, plus ten unrelated distractors.

`test_cluster.py::test_clustering_quality_does_not_regress` pins the headline
number so a refactor cannot silently degrade it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from sklearn.metrics import adjusted_rand_score

from newsanchor.cluster import cluster_articles
from tests.gold import GOLD, gold_articles


def score(threshold: float, *, use_summary: bool = True) -> tuple[float, int]:
    articles, truth = gold_articles(use_summary=use_summary)
    stories = cluster_articles(articles, distance_threshold=threshold)

    predicted = {}
    for label, story in enumerate(stories):
        for article in story.articles:
            predicted[article.url] = label

    pred = np.array([predicted[a.url] for a in articles])
    return adjusted_rand_score(truth, pred), len(stories)


def main() -> None:
    print(f"gold set: {len(GOLD)} stories, {sum(len(v) for v in GOLD)} articles\n")
    for use_summary in (True, False):
        label = "headline + summary" if use_summary else "headline only"
        print(f"--- {label}")
        for threshold in (0.70, 0.75, 0.80, 0.85, 0.88, 0.90):
            ari, n = score(threshold, use_summary=use_summary)
            print(f"    threshold={threshold:.2f}  clusters={n:3d}  ARI={ari:.3f}")
        print()


if __name__ == "__main__":
    main()
