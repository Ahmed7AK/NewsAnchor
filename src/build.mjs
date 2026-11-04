import { mkdir, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { parseFeed } from './parse.mjs';

const USER_AGENT = 'DailyDigest/1.0 (+https://github.com/ahmed7ak/newsanchor)';
const ACCEPT = 'application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5';
const MAX_FEED_BYTES = 5_000_000;
export const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Calendar date (YYYY-MM-DD) of `date` in `timeZone`. */
export function dayKey(date, timeZone) {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone, year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(date);
}

export async function fetchFeed(feed, category, { fetchImpl = fetch, timeoutMs = 20_000 } = {}) {
  const res = await fetchImpl(feed.url, {
    headers: { 'user-agent': USER_AGENT, accept: ACCEPT },
    signal: AbortSignal.timeout(timeoutMs),
    redirect: 'follow',
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const xml = await res.text();
  if (xml.length > MAX_FEED_BYTES) throw new Error('feed too large');
  return parseFeed(xml, { source: feed.source, category, url: res.url || feed.url });
}

export async function fetchAll(config, opts = {}) {
  const jobs = config.categories.flatMap((c) => c.feeds.map((feed) => ({ feed, category: c.id })));
  const results = await Promise.allSettled(jobs.map((j) => fetchFeed(j.feed, j.category, opts)));
  const report = jobs.map(({ feed, category }, i) => {
    const r = results[i];
    return r.status === 'fulfilled'
      ? { source: feed.source, category, url: feed.url, ok: true, count: r.value.length }
      : { source: feed.source, category, url: feed.url, ok: false, error: r.reason?.message || String(r.reason) };
  });
  const stories = results.flatMap((r) => (r.status === 'fulfilled' ? r.value : []));
  return { stories, report };
}

const titleKey = (s) => `${s.source}|${s.title.toLowerCase().replace(/\W+/g, ' ').trim()}`;

/**
 * Fold freshly fetched stories into what has already been collected today.
 * New stories older than `maxAgeHours` are ignored (feeds often carry stale
 * items); stories seen earlier in the day are kept. Each category keeps at
 * most `perCategory` of its newest stories.
 */
export function mergeStories({ existing = [], fresh, now, maxAgeHours = 36, perCategory = 60, categoryOrder = [] }) {
  const nowMs = now.getTime();
  const nowIso = now.toISOString();
  const cutoff = nowMs - maxAgeHours * 3_600_000;
  const byId = new Map();
  const byTitle = new Map();
  const remember = (s) => { byId.set(s.id, s); byTitle.set(titleKey(s), s); };

  for (const s of existing) remember({ ...s, categories: [...s.categories] });

  for (const s of fresh) {
    const t = s.published ? Date.parse(s.published) : nowMs;
    if (t < cutoff) continue;
    const prev = byId.get(s.id) || byTitle.get(titleKey(s));
    if (prev) {
      for (const c of s.categories) if (!prev.categories.includes(c)) prev.categories.push(c);
      prev.title = s.title;
      prev.summary ||= s.summary;
      prev.image ||= s.image;
      continue;
    }
    remember({
      ...s,
      categories: [...s.categories],
      published: t > nowMs ? nowIso : new Date(t).toISOString(),
      firstSeen: nowIso,
    });
  }

  const rank = (c) => { const i = categoryOrder.indexOf(c); return i === -1 ? Infinity : i; };
  const counts = {};
  const kept = [];
  const sorted = [...byId.values()].sort((a, b) => (a.published < b.published ? 1 : a.published > b.published ? -1 : 0));
  for (const s of sorted) {
    s.categories = s.categories
      .filter((c) => (counts[c] = (counts[c] || 0) + 1) <= perCategory)
      .sort((a, b) => rank(a) - rank(b));
    if (s.categories.length) kept.push(s);
  }
  return kept;
}

async function readJson(file) {
  try {
    return JSON.parse(await readFile(file, 'utf8'));
  } catch (err) {
    if (err.code === 'ENOENT') return null;
    throw new Error(`Could not read ${file}: ${err.message}`);
  }
}

/** Pull earlier days from the already-published site so the archive survives fresh CI checkouts. */
async function seedFromArchive(archiveUrl, outDir, fetchImpl, log) {
  const base = archiveUrl.endsWith('/') ? archiveUrl : `${archiveUrl}/`;
  let index;
  try {
    const res = await fetchImpl(new URL('data/index.json', base), { signal: AbortSignal.timeout(20_000) });
    if (!res.ok) { log(`No published archive yet (HTTP ${res.status}); starting fresh.`); return; }
    index = await res.json();
  } catch (err) {
    log(`Could not load published archive (${err.message}); starting fresh.`);
    return;
  }
  let restored = 0;
  for (const { date } of Array.isArray(index?.days) ? index.days : []) {
    if (!DATE_RE.test(String(date))) continue;
    const file = path.join(outDir, `${date}.json`);
    if (await readJson(file)) continue;
    try {
      const res = await fetchImpl(new URL(`data/${date}.json`, base), { signal: AbortSignal.timeout(20_000) });
      if (!res.ok) continue;
      const day = await res.json();
      if (!Array.isArray(day?.stories)) continue;
      await writeFile(file, JSON.stringify(day));
      restored++;
    } catch { /* skip that day */ }
  }
  log(`Restored ${restored} archived day(s) from ${base}`);
}

export async function runFetch({
  configPath, outDir, timeZone, archiveUrl = '', now = new Date(),
  fetchImpl = fetch, log = console.log, keepDays = 30,
}) {
  try {
    new Intl.DateTimeFormat('en-US', { timeZone });
  } catch {
    throw new Error(`Unknown time zone "${timeZone}". Use an IANA name such as "America/New_York".`);
  }
  const config = JSON.parse(await readFile(configPath, 'utf8'));
  await mkdir(outDir, { recursive: true });
  if (archiveUrl) await seedFromArchive(archiveUrl, outDir, fetchImpl, log);

  const { stories: fresh, report } = await fetchAll(config, { fetchImpl });
  const failed = report.filter((r) => !r.ok);
  for (const r of report) {
    log(`${r.ok ? '  ok ' : ' FAIL'}  ${r.category.padEnd(13)} ${r.source.padEnd(16)} ${r.ok ? `${r.count} stories` : r.error}`);
  }
  if (failed.length === report.length) {
    throw new Error('Every feed failed, so existing news files were left untouched.');
  }

  const date = dayKey(now, timeZone);
  const dayFile = path.join(outDir, `${date}.json`);
  const existing = (await readJson(dayFile))?.stories ?? [];
  const categoryOrder = config.categories.map((c) => c.id);
  const stories = mergeStories({ existing, fresh, now, categoryOrder });
  const day = {
    date,
    timeZone,
    updatedAt: now.toISOString(),
    categories: config.categories.map(({ id, label }) => ({ id, label })),
    sources: [...new Set(stories.map((s) => s.source))].sort(),
    stories,
  };
  await writeFile(dayFile, JSON.stringify(day));

  const dates = (await readdir(outDir))
    .map((f) => f.replace(/\.json$/, ''))
    .filter((d) => DATE_RE.test(d))
    .sort()
    .reverse();
  for (const old of dates.slice(keepDays)) await rm(path.join(outDir, `${old}.json`));
  const days = [];
  for (const d of dates.slice(0, keepDays)) {
    const data = d === date ? day : await readJson(path.join(outDir, `${d}.json`));
    if (data) days.push({ date: d, count: data.stories.length, updatedAt: data.updatedAt });
  }
  await writeFile(path.join(outDir, 'index.json'), JSON.stringify({
    latest: date,
    updatedAt: now.toISOString(),
    timeZone,
    days,
    lastRun: {
      at: now.toISOString(),
      feeds: report.length,
      failed: failed.map(({ source, category, error }) => ({ source, category, error })),
    },
  }));

  log(`\n${date}: ${stories.length} stories from ${day.sources.length} sources (${fresh.length} fetched, ${failed.length}/${report.length} feeds failed)`);
  return { date, count: stories.length, failed };
}
