# Public news APIs and bias data: what's actually usable

Research notes behind NewsAnchor's design. Written September 2026. Anything
with a price or a quota in it goes stale fast — re-check before relying on it.

---

## The short version

**Use RSS as the backbone.** Nearly every free news API is either a
prototyping toy (100 requests/day, dev use only) or attributes articles to
whoever re-syndicated them, which destroys the one signal a bias-aware
aggregator depends on. RSS has neither problem.

**Supplement with GDELT** when you want to know a story exists that none of
your outlets ran.

**Don't expect to buy bias ratings cheaply.** The three well-known charts
(AllSides, Ad Fontes, MBFC) all license commercially and none has a free
programmatic tier worth building on.

---

## Article sources

### RSS / Atom feeds — the recommended backbone

| | |
|---|---|
| **Cost** | Free |
| **Key** | None |
| **Quota** | None (be polite: cache, respect `ETag`/`Last-Modified`) |
| **Licence** | Each outlet's terms. Headlines + blurbs + links is the intended use. |
| **Coverage** | ~40 outlets configured in `data/sources.yaml` |

Why this beats the commercial APIs for this particular application:

- **Attribution is unambiguous.** You know exactly which newsroom published
  each item, because you asked that newsroom directly. Aggregator APIs
  routinely hand you an article credited to a syndicating site rather than the
  originating newsroom — which silently corrupts any per-source lean signal.
- **No quota maths.** Forty feeds polled hourly is 960 requests/day, which
  would blow through most free tiers before breakfast and costs nothing here.
- **Graceful degradation.** A dead feed costs you one outlet, not the run.

Real limitations, stated plainly:

- **Headline + blurb only.** No full text. This matters more than it sounds:
  NewsAnchor's clustering measured ARI 0.926 with feed summaries and 0.76 on
  headlines alone (see `backend/tests/benchmark_cluster.py`). Outlets that
  publish description-less feeds cluster noticeably worse.
- **Feeds rot.** Outlets move or kill them without notice. AP and Reuters both
  retired their general public feeds. `newsanchor sources check` exists
  because of this — run it periodically.
- **Coverage is whatever the outlet chose to syndicate**, which is not
  necessarily everything they published.

For full text, add [trafilatura](https://trafilatura.readthedocs.io) (already
an optional dependency) — but check each outlet's terms first, and expect
paywalls to defeat it.

### GDELT DOC 2.0 — free, keyless, enormous

```
https://api.gdeltproject.org/api/v2/doc/doc
  ?query=<terms> sourcelang:eng
  &mode=ArtList        # also: TimelineVol, TimelineTone, ImageCollage, WordCloudTheme
  &maxrecords=250      # hard ceiling
  &timespan=1d         # minutes/hours/days/weeks/months; default 3 months
  &format=json
```

No key, no registration, no documented quota. Indexes worldwide news in 65+
languages, updated every 15 minutes. `TimelineTone` and `TimelineVol` give you
sentiment and volume time series essentially for free.

**What it's good for here:** discovering that a story exists which none of
your subscribed outlets ran. That's a genuine blind-spot detector, and nothing
else free does it at this breadth.

**What it isn't good for:** attribution you'd want to bias-score. GDELT
reports the *domain* that published a piece, frequently a syndicator. Hence
`ingest/gdelt.py` namespaces its articles as `gdelt:<domain>` and never lets
them enter the lean histogram as though they were a rated source.

Note the tone/sentiment fields measure *sentiment*, not *political lean*. A
uniformly grim story reads as strongly negative from every outlet on the
spectrum. Don't conflate the two.

### NewsAPI.org — a prototyping tool, not a foundation

Free "Developer" tier: **100 requests/day, articles delayed ~24 hours, ~1
month of archive, CORS restricted to localhost, development use only —
production and commercial use are forbidden by the terms.**

For a *daily* digest the 24-hour delay is the disqualifier, not the quota.
Paid tiers remove it. Wired up in `ingest/newsapi.py` if you want to compare
coverage; off unless `NEWSAPI_KEY` is set.

### Others worth knowing

| Source | Notes |
|---|---|
| **The Guardian Open Platform** | Genuinely generous free tier, full article text, clean docs, permissive for non-commercial use. Best single-publisher API available. One publisher, so it's a supplement, not a spine. |
| **The New York Times APIs** | Free key, good archive and Top Stories endpoints. Rate-limited; one publisher. |
| **Newsdata.io / Currents / Mediastack / APITube** | Larger free tiers than NewsAPI (a few hundred requests/day). Same attribution caveat: you get the syndicator's domain, not always the originating newsroom. Terms vary — read them before shipping. |
| **Wikipedia Current Events (Wikifeeds API)** | Free, no key. Human-curated daily list of what happened, in 15+ languages. Excellent *cross-check*: if it's on the Current Events portal and absent from your digest, your roster has a hole. |
| **Wikinews** | **Dead.** The Wikimedia Foundation closed it and made it read-only in May 2026. Don't build on it. |
| **AP / Reuters / AFP content APIs** | Enterprise pricing, not realistic for a personal project. They matter anyway as *syndication signatures* — see below. |
| **Common Crawl News** | Enormous historical WARC archive, free. Great for backfill and research, far too heavy for a daily feed. |

### Syndication is the trap

The single most important thing this research turned up:

> If AP files a story and forty outlets run it verbatim, a naive aggregator
> reports *"40 sources across the spectrum covered this."* That is the exact
> opposite of the truth. It is **one newsroom's account, reprinted forty
> times.**

Counting reprints as independent corroboration is the easiest way for a
balance-focused feed to mislead its reader — it manufactures the appearance of
consensus out of a single source. `backend/newsanchor/wires.py` detects wire
credit lines and collapses them before anything is counted; the digest reports
"1 original report, 39 reprints" instead.

Detection is heuristic and deliberately conservative. False negatives cost a
little dedup quality; false positives would wrongly erase a newsroom's own
reporting, which is worse.

---

## Bias and credibility data

This is the weakest part of the landscape, and it's worth being blunt about
it.

| Provider | Coverage | Access |
|---|---|---|
| **AllSides** | ~1,400 sources, 5-point L/R scale, blind-survey methodology | Commercial licence + API. No free programmatic tier. |
| **Ad Fontes Media** | ~2,400 sources, two axes (bias × reliability) | Commercial licence. Static chart free to view. |
| **Media Bias/Fact Check** | ~11,000 sources, bias + factual + credibility | Direct commercial API, or RapidAPI for research/non-commercial. |

There are scraped MBFC/AllSides datasets on GitHub and Kaggle. **NewsAnchor
does not use them**, for two reasons: the licensing is murky at best (the
scrapes inherit the source's terms, which generally prohibit redistribution),
and they go stale silently, which is arguably worse than being absent.

### What NewsAnchor does instead

`data/sources.yaml` ships a **coarse, hand-curated, clearly-labelled** lean
value per source, assembled from the broad consensus of the public charts.
It is explicitly not authoritative, and the file says so at the top. It exists
so the app works out of the box, and it is designed to be edited — the app
reads it at runtime.

If you want real ratings, license one and map it into the same `lean` field.

### Four caveats that shaped the design

1. **A left-right axis is US-centric.** Mapping Al Jazeera or Deutsche Welle
   onto it produces noise, not signal. Non-US outlets carry `lean: null` and
   are balanced on the `country` axis instead of being forced onto a spectrum
   they don't belong to.
2. **Source-level bias is a blunt instrument.** It says nothing about an
   individual article, and it conflates news desks with opinion pages — the
   WSJ is the standard example.
3. **Bias ≠ accuracy.** A source can be dead-center and consistently wrong.
   These are orthogonal axes and NewsAnchor only models one of them.
4. **A balanced feed is not a true feed.** Presenting every story as
   left-vs-right implies both sides are equally supported by evidence, which
   is sometimes false. This is the genuine limitation of the whole approach,
   and no amount of engineering fixes it.

---

## Clustering: what actually worked

Grouping "the same event, as covered by different outlets" is the load-bearing
step — balanced exposure is impossible without it.

**Chosen:** TF-IDF (unigrams) → cosine distance → agglomerative clustering
with average linkage, distance threshold 0.80. Measured **ARI 0.926** against
a hand-labelled 21-story benchmark.

Three findings from the tuning, all reproducible via
`python backend/tests/benchmark_cluster.py`:

- **Bigrams hurt** (ARI 0.53 vs 0.76 headline-only). Outlets rephrase
  constantly, so almost no bigram survives across two newsrooms' versions of
  one event. The ones that do just add noise.
- **Feed summaries carry most of the signal** (0.926 vs 0.76). This is the
  single biggest quality lever, and it's a data property, not a tuning knob.
- **The optimum is a peak, not a plateau.** Drifting to 0.90 costs as much
  accuracy as drifting to 0.70.

**Known failure mode**, pinned as a strict `xfail` in `test_cluster.py`:
same-institution-different-case pairs merge. "Supreme Court agrees to hear
tariff case" and "Supreme Court declines gun rights appeal" share nearly all
their high-weight terms after stopword removal. Bag-of-words has no way to
know `tariff` and `gun` name different disputes. This is the single error
behind 0.926 rather than 1.0, and fixing it needs semantics, not tuning.

**Upgrade path:** swap the vectoriser for sentence embeddings (a multilingual
model would also cluster across languages, which TF-IDF cannot do at all).
Costs a ~90MB model download and a torch dependency, which is why it isn't the
default. The interface in `cluster.py` is unchanged by the swap.

---

## What "bias free" can and cannot mean

Worth stating outright, because it shaped every scoring decision:

**NewsAnchor cannot remove bias, and doesn't claim to.** What it can do is
make the *shape* of the coverage visible — who covered a story, from where,
how many of them were genuinely independent, and which parts of the spectrum
said nothing — and then rank the feed so that stories you'd otherwise only
meet from one direction rise instead of sink.

That last part is the substantive design choice: balance and diversity
*multiply into the ranking* rather than merely being displayed next to it. A
feed ranked on prominence alone just reproduces whatever the loudest cluster
of outlets decided mattered, which is the problem the app exists to solve.

Three things the app deliberately does **not** do:

- **Rewrite articles to be neutral by default.** The optional LLM layer is
  asked to report what sources agree on and to *name where they disagree*, not
  to smooth disagreement away. Disagreement between outlets is signal for the
  reader.
- **Treat state media as ordinary sources.** Outlets under direct government
  editorial control are present but off by default, and loudly labelled when
  enabled. Note this is about editorial control, not funding — the BBC and NPR
  take public money and are not flagged.
- **Hide its own limitations.** The roster is currently lopsided (9 lean-left
  outlets vs 3 lean-right, largely reflecting which outlets publish usable
  RSS). The app reports this on every run rather than letting it quietly skew
  the output, because an under-represented side of the roster looks identical
  to a genuine coverage gap.

---

## Sources

- [GDELT DOC 2.0 API](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/) · [GDELT data](https://www.gdeltproject.org/data.html)
- [NewsAPI.org](https://newsapi.org/pricing)
- [The Guardian Open Platform](https://open-platform.theguardian.com/)
- [NYT Developer APIs](https://developer.nytimes.com/)
- [Wikimedia current-events APIs](https://api.wikimedia.org/wiki/Use_cases/Current_events)
- [AllSides bias ratings licence & API](https://www.allsides.com/tools-services/bias-ratings-license-api)
- [Ad Fontes Media](https://adfontesmedia.com/static-mbc/)
- [Media Bias/Fact Check data API](https://mediabiasfactcheck.com/mbfcs-data-api/)
- [awesome-rss-feeds](https://github.com/plenaryapp/awesome-rss-feeds) · [rss-news-list](https://github.com/vandenbroucke/rss-news-list)
- [Hierarchical news clustering via multilingual embeddings (arXiv 2506.00277)](https://arxiv.org/pdf/2506.00277) · [Real-time news story identification (arXiv 2508.08272)](https://arxiv.org/pdf/2508.08272)
