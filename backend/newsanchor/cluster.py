"""Grouping articles from different outlets into a single story.

This is the load-bearing step. "Balanced exposure" means showing you how the
*same event* was covered across the spectrum, which is only possible if we can
reliably decide that these three headlines are one story:

    "Senate passes spending bill in late-night vote"        (NPR)
    "Congress averts shutdown as Senate clears package"     (Fox News)
    "US Senate approves budget deal, ending standoff"       (Al Jazeera)

Approach: TF-IDF over headline+blurb, cosine distance, agglomerative
clustering with a fixed distance threshold.

Why not embeddings? A sentence-transformer would cluster better, especially
across languages and paraphrase. It also means a ~90MB model download, a torch
dependency, and several seconds per run. TF-IDF gets most of the way on
headlines specifically, because news headlines about the same event share
proper nouns -- and proper nouns are exactly what TF-IDF weights highest.
`embed.py` is the upgrade path when you want it; the interface is the same.

Why agglomerative rather than k-means? We do not know how many stories there
are, and that is the whole question. Agglomerative with a distance threshold
discovers the count. k-means would need it up front.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer

from .models import Article, Story

# Cosine distance above which two articles are considered different stories.
#
# Chosen by sweeping thresholds against a hand-labelled benchmark of 21 stories
# (see tests/benchmark_cluster.py -- run it after any change here). Measured
# adjusted Rand index against the gold labels:
#
#   headline + feed summary     headline only
#   0.75 -> 0.814               0.75 -> 0.535
#   0.80 -> 0.926  <-- default  0.80 -> 0.658
#   0.85 -> 0.833               0.85 -> 0.763
#   0.90 -> 0.672               0.90 -> 0.680
#
# Two things that matters-a-lot fall out of that table:
#
#  1. Feed summaries carry most of the discriminating signal. Headlines alone
#     top out around 0.76 because "Supreme Court agrees to hear tariff case"
#     and "Supreme Court declines gun rights appeal" share nearly all their
#     high-weight terms. If an outlet publishes description-less feeds, its
#     articles will cluster noticeably worse -- that is a data problem, not a
#     tuning problem.
#  2. The optimum is a peak, not a plateau. Drifting to 0.90 costs as much
#     accuracy as drifting to 0.70. Re-run the benchmark before changing it.
DEFAULT_DISTANCE_THRESHOLD = 0.80

# Headline furniture that carries no topical signal but is common enough to
# skew similarity. Outlet names are stripped separately.
BOILERPLATE = re.compile(
    r"\b(?:live\s+updates?|breaking|watch|video|photos?|opinion|analysis|explainer|"
    r"what\s+to\s+know|here'?s\s+what|read\s+more)\b",
    re.I,
)
# Trailing " - BBC News", " | Reuters", " — The Guardian"
TRAILING_OUTLET = re.compile(r"\s*[-|—–]\s*[A-Z][\w.&' ]{2,30}\s*$")


def normalise(text: str) -> str:
    text = TRAILING_OUTLET.sub("", text)
    text = BOILERPLATE.sub(" ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _story_id(articles: list[Article]) -> str:
    """Deterministic id from member URLs, so reruns produce stable ids."""
    joined = "|".join(sorted(a.url for a in articles))
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]


def cluster_articles(
    articles: list[Article],
    *,
    distance_threshold: float = DEFAULT_DISTANCE_THRESHOLD,
    min_sources: int = 1,
) -> list[Story]:
    """Group articles into Stories.

    `min_sources` drops stories carried by fewer than N distinct outlets. The
    default of 1 keeps everything; raise it to 2+ to see only stories that got
    corroborated, which is a decent noise filter on its own.
    """
    if not articles:
        return []

    if len(articles) == 1:
        return [Story(id=_story_id(articles), articles=list(articles))]

    corpus = [normalise(a.text_for_matching) for a in articles]

    vectoriser = TfidfVectorizer(
        # Unigrams only. Bigrams were measurably worse (ARI 0.53 vs 0.76 on the
        # headline-only benchmark): outlets rephrase constantly, so almost no
        # bigram survives across two newsrooms' versions of the same event,
        # and the ones that do just add noise to the denominator.
        ngram_range=(1, 1),
        # A term appearing in a single article cannot link two articles, but
        # dropping it entirely (min_df=2) discards rare proper nouns that are
        # the strongest signal we have. Keep them.
        min_df=1,
        # Terms appearing in >50% of a day's articles are furniture, not topic.
        # But on a tiny corpus that ratio is destructive: with 3 documents it
        # discards every term shared by 2 of them -- i.e. exactly the terms
        # that would have linked them. Only apply it once there is enough
        # corpus for "appears everywhere" to mean anything.
        max_df=0.5 if len(corpus) >= 10 else 1.0,
        sublinear_tf=True,
        stop_words="english",
    )

    try:
        matrix = vectoriser.fit_transform(corpus)
    except ValueError:
        # Every document was empty after normalisation.
        return [Story(id=_story_id([a]), articles=[a]) for a in articles]

    if matrix.shape[1] == 0:
        return [Story(id=_story_id([a]), articles=[a]) for a in articles]

    dense = matrix.toarray().astype(np.float64)

    # Rows that normalised to nothing have zero norm; cosine distance against
    # them is undefined and sklearn will emit NaNs that poison the linkage.
    norms = np.linalg.norm(dense, axis=1)
    live_idx = np.flatnonzero(norms > 0)
    dead_idx = np.flatnonzero(norms == 0)

    stories: list[Story] = [Story(id=_story_id([articles[i]]), articles=[articles[i]])
                            for i in dead_idx]

    if len(live_idx) == 1:
        i = int(live_idx[0])
        stories.append(Story(id=_story_id([articles[i]]), articles=[articles[i]]))
    elif len(live_idx) > 1:
        model = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=distance_threshold,
            metric="cosine",
            # 'average' is the right call here: 'single' chains unrelated
            # stories together through one shared proper noun, 'complete' is
            # too eager to split a story whose outlier headline is terse.
            linkage="average",
        )
        labels = model.fit_predict(dense[live_idx])

        grouped: dict[int, list[Article]] = defaultdict(list)
        for label, idx in zip(labels, live_idx):
            grouped[int(label)].append(articles[int(idx)])

        for members in grouped.values():
            members.sort(key=lambda a: a.published_at)
            stories.append(Story(id=_story_id(members), articles=members))

    if min_sources > 1:
        stories = [s for s in stories if len(s.source_ids) >= min_sources]

    stories.sort(key=lambda s: (len(s.source_ids), s.newest), reverse=True)
    return stories
