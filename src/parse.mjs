import { createHash } from 'node:crypto';
import { XMLParser } from 'fast-xml-parser';
import { canonicalUrl, firstImageSrc, safeUrl, toPlainText, truncate } from './text.mjs';

const ALWAYS_ARRAY = new Set([
  'item', 'entry', 'link', 'enclosure', 'media:content', 'media:thumbnail', 'media:group',
]);

// Entities are left alone here and decoded by our own text helpers, which
// also means DOCTYPE-declared entities are never expanded.
const parser = new XMLParser({
  ignoreAttributes: false,
  attributeNamePrefix: '@_',
  processEntities: false,
  parseTagValue: false,
  parseAttributeValue: false,
  trimValues: true,
  isArray: (name) => ALWAYS_ARRAY.has(name),
});

const SUMMARY_MAX = 280;

const asArray = (v) => (v == null ? [] : Array.isArray(v) ? v : [v]);

function text(v) {
  if (v == null) return '';
  if (Array.isArray(v)) return text(v[0]);
  if (typeof v === 'object') return v['#text'] == null ? '' : String(v['#text']);
  return String(v);
}

function pickLargest(nodes) {
  let best = null;
  for (const n of nodes) {
    if (!n || !n['@_url']) continue;
    const medium = n['@_medium'];
    const type = n['@_type'] || '';
    if (medium && medium !== 'image') continue;
    if (!medium && type && !type.startsWith('image/')) continue;
    const width = Number(n['@_width']) || 0;
    if (!best || width > best.width) best = { url: n['@_url'], width };
  }
  return best?.url ?? null;
}

function imageFor(node, html, base) {
  const groups = asArray(node['media:group']);
  const media = [...asArray(node['media:content']), ...groups.flatMap((g) => asArray(g['media:content']))];
  const thumbs = [...asArray(node['media:thumbnail']), ...groups.flatMap((g) => asArray(g['media:thumbnail']))];
  const enclosures = asArray(node.enclosure).filter((e) => String(e['@_type'] || '').startsWith('image/'));
  const candidate =
    pickLargest(media) ||
    pickLargest(thumbs.map((t) => ({ ...t, '@_medium': 'image' }))) ||
    enclosures[0]?.['@_url'] ||
    firstImageSrc(html);
  return safeUrl(candidate, base);
}

function rssEntry(it, base) {
  const linkText = asArray(it.link).map(text).find(Boolean);
  const guid = it.guid;
  const guidIsLink = typeof guid === 'object' ? guid['@_isPermaLink'] !== 'false' : true;
  const content = text(it['content:encoded']);
  const description = text(it.description);
  return {
    title: text(it.title),
    link: linkText || (guidIsLink ? text(guid) : '') || it['@_rdf:about'],
    published: text(it.pubDate) || text(it['dc:date']) || text(it.published) || text(it.updated),
    summaryHtml: description || content,
    image: imageFor(it, content || description, base),
  };
}

function atomEntry(e, base) {
  const links = asArray(e.link);
  const alt = links.find((l) => !l['@_rel'] || l['@_rel'] === 'alternate') || links[0];
  const content = text(e.content);
  const summary = text(e.summary);
  return {
    title: text(e.title),
    link: alt?.['@_href'] ?? text(alt),
    published: text(e.published) || text(e.updated),
    summaryHtml: summary || content,
    image: imageFor(e, content || summary, base),
  };
}

function toIso(value) {
  if (!value) return null;
  const d = new Date(value.trim());
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

export function storyId(link) {
  return createHash('sha1').update(canonicalUrl(link)).digest('hex').slice(0, 12);
}

/**
 * Parse RSS 2.0, RSS 1.0 (RDF) or Atom XML into normalised stories.
 * Entries without a usable title or http(s) link are dropped.
 */
export function parseFeed(xml, { source, category, url: feedUrl } = {}) {
  const doc = parser.parse(xml);
  let entries;
  if (doc.rss) {
    entries = asArray(doc.rss.channel).flatMap((c) => asArray(c.item)).map((it) => rssEntry(it, feedUrl));
  } else if (doc.feed) {
    entries = asArray(doc.feed.entry).map((e) => atomEntry(e, feedUrl));
  } else if (doc['rdf:RDF']) {
    entries = asArray(doc['rdf:RDF'].item).map((it) => rssEntry(it, feedUrl));
  } else {
    throw new Error('Not an RSS or Atom feed');
  }

  const stories = [];
  for (const e of entries) {
    const title = toPlainText(e.title);
    const link = safeUrl(e.link, feedUrl);
    if (!title || !link) continue;
    const summary = truncate(toPlainText(e.summaryHtml), SUMMARY_MAX);
    stories.push({
      id: storyId(link),
      title,
      link,
      source,
      categories: category ? [category] : [],
      published: toIso(e.published),
      summary: summary === title ? '' : summary,
      image: e.image,
    });
  }
  return stories;
}
