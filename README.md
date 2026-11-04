# Daily Digest

A web app that gathers each day's news from public RSS feeds into one clean, fast page, with Top Stories, World, Business, Technology, Science, Health, Sports, and Entertainment sections.

- **Today's news at a glance:** a lead story, the next few headlines, then everything else as cards.
- **Refreshes through the day:** new stories are added to today's page; nothing you saw earlier disappears.
- **Archive:** step back through the last 30 days with the day picker or the ‹ › buttons.
- **Search** across every section (press `/`), **"New" badges** for stories since your last visit, and **read tracking**, with an option to hide stories you've already opened.
- Works on phones, follows your light/dark setting, and needs no accounts or API keys.

## Run it on your computer

Requires [Node.js](https://nodejs.org) 20 or newer.

```bash
npm install
npm start
```

Open <http://localhost:3000>. `npm start` fetches the news right away and again every hour while it runs.

Other commands:

| Command | What it does |
| --- | --- |
| `npm run fetch` | Fetch the news once into `public/data/` |
| `npm run serve` | Serve the site without fetching |
| `npm test` | Run the tests |

Environment variables: `PORT` (default 3000), `NEWS_TZ`, an IANA time zone that decides when "today" starts (default: your computer's), and `FEEDS_FILE`, an alternative feed list.

## Get a link that updates itself (GitHub Pages)

The included workflow, `.github/workflows/daily-news.yml`, fetches the news four times a day and publishes the site for free on GitHub Pages:

1. Push this repository to GitHub.
2. Go to **Settings → Pages** and set **Source** to **GitHub Actions**.
3. Optional: under **Settings → Secrets and variables → Actions → Variables**, add `NEWS_TZ` with your time zone (for example `America/New_York` or `Europe/London`). The default is UTC.
4. Go to **Actions → Daily news → Run workflow** to publish the first edition.

Your site will be at `https://<your-username>.github.io/<repo-name>/`. To change how often it refreshes, edit the `cron` line in the workflow. GitHub Pages on private repositories needs a paid GitHub plan, and GitHub pauses scheduled workflows in repositories that have had no activity for 60 days.

## Choosing your sources

Edit `feeds.json`. Each section has an `id`, a `label` and a list of feeds:

```json
{ "source": "BBC News", "url": "https://feeds.bbci.co.uk/news/rss.xml" }
```

Any RSS or Atom feed works. Add, remove or reorder sections freely; the tabs follow this file. If a feed is down, the rest still update and the page notes how many feeds were unavailable.

## How it works

```
feeds.json ──► scripts/fetch-news.mjs ──► public/data/YYYY-MM-DD.json + index.json ──► public/ (static page)
```

- `src/parse.mjs` turns RSS 2.0, RSS 1.0 and Atom into plain-text stories. Only `http(s)` links and images are kept, and nothing from a feed is ever inserted into the page as HTML.
- `src/build.mjs` merges each run into the day's file. It removes duplicates across feeds, skips items older than 36 hours, keeps the newest 60 per section and keeps 30 days of history.
- `public/` is a plain HTML/CSS/JS page with no build step, so any static host can serve it.

Headlines and summaries belong to their publishers; every story links to the original article.
