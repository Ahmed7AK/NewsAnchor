// Small, dependency-free helpers for turning feed markup into plain text.

const NAMED = {
  amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ',
  hellip: '…', mdash: '—', ndash: '–', lsquo: '‘', rsquo: '’',
  ldquo: '“', rdquo: '”', laquo: '«', raquo: '»', bull: '•',
  middot: '·', copy: '©', reg: '®', trade: '™', deg: '°',
  pound: '£', euro: '€', yen: '¥', cent: '¢', times: '×',
  eacute: 'é', egrave: 'è', aacute: 'á', agrave: 'à', iacute: 'í',
  oacute: 'ó', uacute: 'ú', ntilde: 'ñ', ccedil: 'ç', uuml: 'ü',
  ouml: 'ö', auml: 'ä', szlig: 'ß', thinsp: ' ', ensp: ' ', emsp: ' ',
  zwj: '', zwnj: '', shy: '',
};

export function decodeEntities(input) {
  return String(input).replace(/&(#x[0-9a-f]+|#\d+|[a-z][a-z0-9]*);/gi, (match, body) => {
    if (body[0] === '#') {
      const hex = body[1] === 'x' || body[1] === 'X';
      const cp = parseInt(body.slice(hex ? 2 : 1), hex ? 16 : 10);
      return Number.isFinite(cp) && cp > 0 && cp <= 0x10ffff ? String.fromCodePoint(cp) : match;
    }
    const named = NAMED[body.toLowerCase()];
    return named === undefined ? match : named;
  });
}

const TAG = /<\/?[a-z!][^>]*>/gi;

// Feeds deliver HTML either inside CDATA or entity-escaped, sometimes both.
// Decode, strip tags, decode again so either shape ends up as clean text.
export function toPlainText(input) {
  if (input == null) return '';
  let s = decodeEntities(String(input));
  s = s.replace(/<(script|style)\b[\s\S]*?<\/\1>/gi, ' ').replace(TAG, ' ');
  s = decodeEntities(s).replace(TAG, ' ');
  return s.replace(/\s+/g, ' ').trim();
}

export function truncate(text, max) {
  if (text.length <= max) return text;
  const cut = text.slice(0, max);
  const space = cut.lastIndexOf(' ');
  const base = space > max * 0.6 ? cut.slice(0, space) : cut;
  return base.replace(/[\s,.;:–—-]+$/, '') + '…';
}

export function firstImageSrc(html) {
  if (!html) return null;
  const decoded = decodeEntities(String(html));
  const m = /<img\b[^>]*?\bsrc\s*=\s*["']([^"']+)["']/i.exec(decoded);
  return m ? m[1] : null;
}

// Only http(s) URLs ever make it into the data the browser renders.
export function safeUrl(raw, base) {
  if (!raw) return null;
  try {
    const url = new URL(decodeEntities(String(raw)).trim(), base);
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : null;
  } catch {
    return null;
  }
}

// A stable key for spotting the same article across feeds: drop tracking
// params, fragments, "www." and trailing slashes.
export function canonicalUrl(href) {
  const url = new URL(href);
  url.hash = '';
  for (const key of [...url.searchParams.keys()]) {
    if (/^(utm_|at_|cmp|ito|ns_|ocid|fbclid|gclid)/i.test(key)) url.searchParams.delete(key);
  }
  url.hostname = url.hostname.replace(/^www\./, '');
  url.protocol = 'https:';
  return url.href.replace(/\/+$/, '');
}
