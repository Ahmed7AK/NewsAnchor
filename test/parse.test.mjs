import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { parseFeed, storyId } from '../src/parse.mjs';
import { canonicalUrl, toPlainText, truncate } from '../src/text.mjs';

const fixture = (name) => readFileSync(new URL(`./fixtures/${name}`, import.meta.url), 'utf8');
const meta = { source: 'Example', category: 'top', url: 'https://example.com/feed.xml' };

test('parses RSS 2.0 items into clean stories', () => {
  const stories = parseFeed(fixture('rss.xml'), meta);
  assert.equal(stories.length, 3, 'drops the javascript: link and the untitled item');

  const [first, second, third] = stories;
  assert.equal(first.title, 'Markets rally as AT&T beats forecasts');
  assert.equal(first.summary, 'Shares rose 3% on Tuesday after the results.');
  assert.equal(first.published, '2026-11-03T14:30:00.000Z');
  assert.equal(first.image, 'https://img.example.com/large.jpg', 'picks the widest thumbnail');
  assert.deepEqual(first.categories, ['top']);
  assert.equal(first.source, 'Example');

  assert.equal(second.title, 'Escaped & double-encoded title – part 2');
  assert.equal(second.link, 'https://example.com/story-2', 'falls back to a permalink guid');
  assert.equal(second.summary, 'Escaped HTML summary & more');
  assert.equal(second.published, '2026-11-03T09:00:00.000Z', 'reads dc:date with offset');
  assert.equal(second.image, 'https://img.example.com/inline.jpg', 'finds an inline <img>');

  assert.equal(third.link, 'https://example.com/relative/path', 'resolves relative links');
  assert.equal(third.published, null, 'invalid dates become null');
  assert.equal(third.image, 'https://img.example.com/enc.png', 'uses image enclosures, ignores video');
  assert.ok(!third.title.includes('BOOM'), 'does not expand DOCTYPE entities');
});

test('parses Atom entries', () => {
  const [chip, updatedOnly] = parseFeed(fixture('atom.xml'), meta);
  assert.equal(chip.title, 'New chip doubles battery life');
  assert.equal(chip.link, 'https://tech.example.com/chip', 'prefers rel=alternate');
  assert.equal(chip.published, '2026-11-04T08:15:00.000Z', 'prefers published over updated');
  assert.equal(chip.summary, 'The new design cuts power draw in half.');
  assert.equal(chip.image, 'https://cdn.example.com/chip.jpg?w=1200&h=800');
  assert.equal(updatedOnly.published, '2026-11-04T07:00:00.000Z');
  assert.equal(updatedOnly.image, null);
});

test('parses RSS 1.0 (RDF) items', () => {
  const [story] = parseFeed(fixture('rdf.xml'), meta);
  assert.equal(story.title, 'RDF story');
  assert.equal(story.published, '2026-11-04T06:00:00.000Z');
});

test('rejects documents that are not feeds', () => {
  assert.throws(() => parseFeed('<html><body>Not a feed</body></html>', meta), /Not an RSS or Atom feed/);
});

test('story ids ignore tracking parameters and www', () => {
  assert.equal(
    storyId('https://www.example.com/a?at_medium=RSS&utm_source=x'),
    storyId('http://example.com/a/'),
  );
  assert.notEqual(storyId('https://example.com/a?id=1'), storyId('https://example.com/a?id=2'));
  assert.equal(canonicalUrl('https://www.example.com/a/?utm_campaign=z#top'), 'https://example.com/a');
});

test('text helpers', () => {
  assert.equal(toPlainText('<p>Hello&nbsp;<b>world</b></p>\n<script>evil()</script>'), 'Hello world');
  assert.equal(toPlainText('3 &lt; 4 &#x26; 5 &gt; 2'), '3 < 4 & 5 > 2');
  assert.equal(truncate('alpha beta gamma delta', 14), 'alpha beta…');
  assert.equal(truncate('short', 10), 'short');
});
