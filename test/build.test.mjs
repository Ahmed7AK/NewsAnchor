import assert from 'node:assert/strict';
import { mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import { dayKey, mergeStories, runFetch } from '../src/build.mjs';

const now = new Date('2026-11-04T12:00:00Z');
const hoursAgo = (h) => new Date(now.getTime() - h * 3_600_000).toISOString();
const story = (id, published, categories = ['top'], extra = {}) => ({
  id, title: `Story ${id}`, link: `https://example.com/${id}`, source: 'Example',
  categories, published, summary: '', image: null, ...extra,
});

test('dayKey uses the configured time zone', () => {
  const t = new Date('2026-11-04T03:00:00Z');
  assert.equal(dayKey(t, 'UTC'), '2026-11-04');
  assert.equal(dayKey(t, 'America/Los_Angeles'), '2026-11-03');
  assert.equal(dayKey(t, 'Asia/Tokyo'), '2026-11-04');
});

test('mergeStories keeps earlier stories, drops stale new ones, and sorts newest first', () => {
  const existing = [{ ...story('early', hoursAgo(40)), firstSeen: hoursAgo(5) }];
  const fresh = [
    story('new', hoursAgo(1)),
    story('stale', hoursAgo(48)),
    story('undated', null),
    story('future', new Date(now.getTime() + 3_600_000).toISOString()),
  ];
  const out = mergeStories({ existing, fresh, now });
  assert.deepEqual(out.map((s) => s.id).slice(2), ['new', 'early']);
  assert.ok(!out.some((s) => s.id === 'stale'), 'stale fresh items are skipped');
  assert.ok(out.some((s) => s.id === 'early'), 'items collected earlier today are kept');
  assert.equal(out.find((s) => s.id === 'future').published, now.toISOString(), 'future dates are clamped');
  assert.equal(out.find((s) => s.id === 'undated').published, now.toISOString());
  assert.equal(out.find((s) => s.id === 'new').firstSeen, now.toISOString());
  assert.equal(out.find((s) => s.id === 'early').firstSeen, hoursAgo(5), 'firstSeen is preserved');
  const times = out.map((s) => s.published);
  assert.deepEqual(times, [...times].sort().reverse());
});

test('mergeStories combines duplicates across sections and caps each section', () => {
  const fresh = [
    story('a', hoursAgo(1), ['world']),
    story('a', hoursAgo(1), ['top'], { image: 'https://img.example.com/a.jpg' }),
    { ...story('b', hoursAgo(2), ['top']), title: 'Same Headline!' },
    { ...story('c', hoursAgo(2), ['business']), title: 'same headline' },
    ...Array.from({ length: 5 }, (_, i) => story(`w${i}`, hoursAgo(3 + i), ['world'])),
  ];
  const out = mergeStories({ existing: [], fresh, now, perCategory: 3, categoryOrder: ['top', 'world', 'business'] });
  const a = out.find((s) => s.id === 'a');
  assert.deepEqual(a.categories, ['top', 'world'], 'sections merged and ordered');
  assert.equal(a.image, 'https://img.example.com/a.jpg');
  assert.ok(!out.some((s) => s.id === 'c'), 'same source + same headline is one story');
  assert.deepEqual(out.find((s) => s.id === 'b').categories, ['top', 'business']);
  assert.equal(out.filter((s) => s.categories.includes('world')).length, 3);
});

function fakeFetch(routes) {
  return async (url) => {
    const body = routes[String(url)];
    if (body === undefined) return new Response('nope', { status: 404 });
    if (body instanceof Error) throw body;
    return new Response(typeof body === 'string' ? body : JSON.stringify(body), { status: 200 });
  };
}

const rss = (items) => `<?xml version="1.0"?><rss version="2.0"><channel><title>T</title>${items
  .map((i) => `<item><title>${i.title}</title><link>${i.link}</link><pubDate>${i.date}</pubDate></item>`)
  .join('')}</channel></rss>`;

test('runFetch writes the day file and index, merges reruns, prunes and restores the archive', async () => {
  const dir = await mkdtemp(path.join(tmpdir(), 'digest-'));
  const outDir = path.join(dir, 'data');
  const configPath = path.join(dir, 'feeds.json');
  await writeFile(configPath, JSON.stringify({
    categories: [
      { id: 'top', label: 'Top Stories', feeds: [{ source: 'A', url: 'https://a.test/rss' }, { source: 'B', url: 'https://b.test/rss' }] },
      { id: 'world', label: 'World', feeds: [{ source: 'A', url: 'https://a.test/world' }] },
    ],
  }));
  const log = () => {};
  try {
    const routes = {
      'https://a.test/rss': rss([{ title: 'One', link: 'https://a.test/1', date: hoursAgo(1) }]),
      'https://a.test/world': rss([{ title: 'One', link: 'https://a.test/1', date: hoursAgo(1) }]),
      'https://b.test/rss': new Error('network down'),
      'https://site.test/data/index.json': { days: [{ date: '2026-11-03' }, { date: '../../evil' }, { date: '2026-10-01' }] },
      'https://site.test/data/2026-11-03.json': { date: '2026-11-03', updatedAt: hoursAgo(20), stories: [story('old', hoursAgo(20))] },
      'https://site.test/data/2026-10-01.json': { date: '2026-10-01', updatedAt: hoursAgo(800), stories: [] },
    };
    const first = await runFetch({
      configPath, outDir, timeZone: 'UTC', now, log, keepDays: 2,
      archiveUrl: 'https://site.test', fetchImpl: fakeFetch(routes),
    });
    assert.equal(first.date, '2026-11-04');
    assert.equal(first.count, 1);
    assert.equal(first.failed.length, 1);

    const files = (await readdir(outDir)).sort();
    assert.deepEqual(files, ['2026-11-03.json', '2026-11-04.json', 'index.json'], 'restored, pruned to keepDays, no traversal');

    const day = JSON.parse(await readFile(path.join(outDir, '2026-11-04.json'), 'utf8'));
    assert.deepEqual(day.stories[0].categories, ['top', 'world']);
    assert.deepEqual(day.sources, ['A']);
    assert.deepEqual(day.categories, [{ id: 'top', label: 'Top Stories' }, { id: 'world', label: 'World' }]);

    const index = JSON.parse(await readFile(path.join(outDir, 'index.json'), 'utf8'));
    assert.equal(index.latest, '2026-11-04');
    assert.deepEqual(index.days.map((d) => d.date), ['2026-11-04', '2026-11-03']);
    assert.equal(index.lastRun.failed[0].source, 'B');

    // A later run the same day adds to, rather than replaces, the day's stories.
    routes['https://a.test/rss'] = rss([{ title: 'Two', link: 'https://a.test/2', date: hoursAgo(0.5) }]);
    const later = new Date(now.getTime() + 3_600_000);
    const second = await runFetch({ configPath, outDir, timeZone: 'UTC', now: later, log, fetchImpl: fakeFetch(routes) });
    assert.equal(second.count, 2);

    // If every feed fails, nothing is overwritten.
    const before = await readFile(path.join(outDir, 'index.json'), 'utf8');
    await assert.rejects(
      runFetch({ configPath, outDir, timeZone: 'UTC', now: later, log, fetchImpl: fakeFetch({}) }),
      /Every feed failed/,
    );
    assert.equal(await readFile(path.join(outDir, 'index.json'), 'utf8'), before);

    await assert.rejects(runFetch({ configPath, outDir, timeZone: 'Mars/Base', log }), /Unknown time zone/);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
