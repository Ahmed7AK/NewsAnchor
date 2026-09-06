# NewsAnchor

A daily news feed assembled for **balanced exposure** and **source diversity**.

It polls ~40 outlets across the political spectrum and several countries,
groups the articles into stories, and shows you each story as *how each side
reported it* — with the parts of the spectrum that said nothing marked
explicitly.

```
 1. Senate passes spending bill in late-night vote
    -  |#  |#  |#  |#     balance 0.86  diversity 0.61  4 outlets  silent: left
       lean-left  NPR: Senate passes spending bill in late-night vote
          center  Axios: Senate approves spending bill, ending shutdown standoff
      lean-right  The Wall Street Journal: Senate clears spending bill in late vote
           right  Fox News: Congress averts shutdown as Senate clears spending package

 4. Cyclone makes landfall in Queensland
    -  |-  |#  |-  |-     balance 0.00  diversity 0.16  3 outlets, 3 reprints
          center  Associated Press: Cyclone makes landfall in Queensland (reprinted by 3 outlets)
```

Note the second card. Three outlets "covered" it — but all three ran the same
AP dispatch. That's one newsroom's account, not three, and the app says so
rather than counting it as broad cross-spectrum agreement.

## What it does

- **Side-by-side coverage.** Every story shows one headline per spectrum
  position, so you see the framing differences directly.
- **Coverage gaps.** Positions we *do* poll that published nothing on a story
  get flagged.
- **Wire collapse.** Syndicated reprints are detected and counted as the one
  newsroom they came from.
- **Balance-weighted ranking.** Balance and diversity feed into the ordering,
  not just the display — otherwise the feed just reproduces whatever the
  loudest outlets decided mattered.
- **Honesty about itself.** It reports its own roster imbalance, and tracks
  what your feed has *actually* consisted of over time.

## What it does not do

It does not remove bias — that isn't possible, and anything claiming otherwise
is selling something. It makes the *shape* of coverage visible so you can
judge for yourself.

A balanced feed is also not a *true* feed: presenting every story as
left-vs-right implies both sides are equally supported by evidence, which is
sometimes false. That's a real limitation of the approach, not a bug to be
fixed. See [docs/RESEARCH.md](docs/RESEARCH.md).

## Quick start

Runs with **no API keys and no accounts**.

```bash
# backend
cd backend
uv venv .venv && source .venv/bin/activate     # or: python -m venv .venv
uv pip install -e ".[dev]"

newsanchor sources check      # verify feed URLs resolve (some will be dead)
newsanchor refresh            # fetch the last 24h and print the digest
```

For the web UI, run the API and the frontend together:

```bash
newsanchor serve                          # terminal 1 -> :8000
cd frontend && npm install && npm run dev # terminal 2 -> :5173
```

### Commands

| Command | What it does |
|---|---|
| `newsanchor refresh` | Fetch all feeds, build and store today's digest |
| `newsanchor show` | Print the stored digest (no network) |
| `newsanchor sources check` | Probe every feed URL and report dead ones |
| `newsanchor sources balance` | How well the roster covers the spectrum |
| `newsanchor balance` | What your feed has actually consisted of |
| `newsanchor serve` | Run the API for the frontend |

The frontend proxies `/api` to `http://127.0.0.1:8000` by default; override
with `NEWSANCHOR_API=http://127.0.0.1:9000 npm run dev`.

Useful flags: `--window-hours`, `--min-sources 2` (only corroborated
stories), `--include-state-affiliated`, `--summarise`.

### Optional: neutral summaries

```bash
uv pip install -e ".[llm]"
export ANTHROPIC_API_KEY=...
newsanchor refresh --summarise
```

The model is asked to report what the sources agree on and to *name where they
disagree* — not to "remove bias", which would just substitute its judgement
for the outlets'. Everything else works without it.

## Configuration

**[`data/sources.yaml`](data/sources.yaml) is the file you'll actually edit.**
It's the single place deciding who gets listened to and how they're weighted;
the app reads it at runtime.

```yaml
- id: npr
  name: NPR
  lean: -1          # -2 left … +2 right, or null if the axis doesn't fit
  tier: nonprofit   # wire | national | magazine | nonprofit | intl
  country: US
  feeds:
    - https://feeds.npr.org/1001/rss.xml
```

The shipped `lean` values are a **coarse editorial starting point**, not
licensed ratings, and they say nothing about accuracy. Disagree with one?
Change it.

State-affiliated outlets (Xinhua, TASS, Global Times) are included but
**disabled by default**, so you can see how state media is framing a story
without that framing quietly entering your feed as independent reporting.

## Known limitations

- **The roster is lopsided** — 9 lean-left outlets vs 3 lean-right, largely
  because of which outlets publish usable RSS. The app warns about this on
  every run. Adding right-leaning sources with working feeds is the single
  highest-value contribution.
- **Feed URLs rot constantly** and were not verifiable from the environment
  this was authored in. Run `newsanchor sources check` first; expect a few
  dead on arrival.
- **Clustering merges same-institution-different-case stories** (two separate
  Supreme Court actions, say). Measured, pinned as a strict `xfail`, and
  explained in `backend/newsanchor/cluster.py`.
- **Headline + blurb only.** Outlets with description-less feeds cluster
  measurably worse (ARI 0.76 vs 0.926).
- **No live run has ever happened.** Everything is verified against synthetic
  fixtures and a browser smoke test. The first real fetch will be on your
  machine — see "Known limitations" above about feed rot.

## Architecture

```
data/sources.yaml         the roster: who we listen to, and their lean
backend/newsanchor/
  ingest/                 rss.py (backbone) · gdelt.py · newsapi.py (optional)
  wires.py                syndicated-reprint detection
  cluster.py              TF-IDF + agglomerative clustering into stories
  balance.py              balance / diversity / prominence scoring + ranking
  digest.py               the pipeline: fetch -> annotate -> cluster -> score
  db.py                   SQLite history
  api.py, cli.py          HTTP API and terminal UI
  llm.py                  optional neutral summaries
frontend/                 React + Vite
docs/RESEARCH.md          the API and bias-data research behind all of this
```

The pipeline is a sequence of near-pure transformations; `run_digest` is the
only function that touches the network, which is what makes the rest testable
offline.

## Development

```bash
cd backend
python -m pytest tests/ -q            # 59 tests, no network required
python tests/benchmark_cluster.py     # clustering quality sweep
ruff check newsanchor tests

cd ../frontend
npm run lint && npm run build
npm run smoke                         # renders the app in Chromium; needs
                                      # `newsanchor serve` + `npm run dev`
```

Change anything in `cluster.py` and re-run the benchmark — a regression test
pins the measured ARI so quality can't silently degrade.
