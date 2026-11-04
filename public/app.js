'use strict';

(() => {
  const REFRESH_MS = 10 * 60 * 1000;
  const LEAD_SIDE_COUNT = 4;

  const $ = (id) => document.getElementById(id);
  const els = {
    dateline: $('dateline'), meta: $('meta'), tabs: $('tabs'), day: $('day'),
    older: $('older'), newer: $('newer'), q: $('q'), hideRead: $('hideRead'),
    notice: $('notice'), lead: $('lead'), moreHeading: $('moreHeading'),
    grid: $('grid'), empty: $('empty'), sources: $('sources'),
  };

  // Per-browser conveniences only; everything works if storage is unavailable.
  const store = {
    get(key, fallback, area = 'localStorage') {
      try {
        const raw = window[area].getItem(key);
        return raw == null ? fallback : JSON.parse(raw);
      } catch { return fallback; }
    },
    set(key, value, area = 'localStorage') {
      try { window[area].setItem(key, JSON.stringify(value)); } catch { /* ignore */ }
    },
  };

  // "New" means first seen since your previous visit; reloads keep the same baseline.
  const since = store.get('dd.since', null, 'sessionStorage') ?? store.get('dd.lastVisit', null);
  store.set('dd.since', since, 'sessionStorage');
  store.set('dd.lastVisit', new Date().toISOString());

  const readIds = new Set(store.get('dd.read', []));
  const state = {
    index: null,
    day: null,
    date: null,
    cat: 'top',
    q: '',
    hideRead: store.get('dd.hideRead', false),
  };

  // ---------------------------------------------------------------- helpers

  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === 'class') node.className = v;
      else if (k === 'text') node.textContent = v;
      else node.setAttribute(k, v === true ? '' : v);
    }
    for (const c of children.flat()) if (c != null) node.append(c);
    return node;
  }

  const isHttp = (u) => typeof u === 'string' && /^https?:\/\//i.test(u);

  function parseDate(key) {
    const [y, m, d] = key.split('-').map(Number);
    return new Date(y, m - 1, d);
  }

  function localKey(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  }

  function dayLabel(key, style = 'short') {
    const today = new Date();
    const yesterday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1);
    if (key === localKey(today)) return 'Today';
    if (key === localKey(yesterday)) return 'Yesterday';
    return parseDate(key).toLocaleDateString(undefined, style === 'short'
      ? { weekday: 'short', month: 'short', day: 'numeric' }
      : { weekday: 'long', month: 'long', day: 'numeric' });
  }

  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto', style: 'short' });
  function relativeTime(iso) {
    const diff = (Date.parse(iso) - Date.now()) / 1000;
    const abs = Math.abs(diff);
    if (abs < 60) return 'just now';
    if (abs < 3600) return rtf.format(Math.round(diff / 60), 'minute');
    if (abs < 86400) return rtf.format(Math.round(diff / 3600), 'hour');
    return rtf.format(Math.round(diff / 86400), 'day');
  }

  function storyTime(iso) {
    if (!iso) return '';
    const isLatest = state.date === state.index?.latest;
    return isLatest
      ? relativeTime(iso)
      : new Date(iso).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
  }

  async function getJson(path) {
    const res = await fetch(path, { cache: 'no-cache' });
    if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
    return res.json();
  }

  function markRead(id, node) {
    if (readIds.has(id)) return;
    readIds.add(id);
    node.classList.add('is-read');
    store.set('dd.read', [...readIds].slice(-3000));
  }

  // ---------------------------------------------------------------- routing

  function readHash() {
    const parts = decodeURIComponent(location.hash.slice(1)).split('/').filter(Boolean);
    let date = null;
    let cat = null;
    for (const p of parts) {
      if (/^\d{4}-\d{2}-\d{2}$/.test(p)) date = p;
      else cat = p;
    }
    return { date, cat };
  }

  function writeHash() {
    const parts = [];
    if (state.date && state.date !== state.index?.latest) parts.push(state.date);
    if (state.cat !== 'top') parts.push(state.cat);
    history.replaceState(null, '', parts.length ? `#${parts.join('/')}` : location.pathname + location.search);
  }

  // ---------------------------------------------------------------- rendering

  function storyNode(s, variant, { showSection = false } = {}) {
    const isNew = since && s.firstSeen && s.firstSeen > since && state.date === state.index?.latest;
    const a = el('a', {
      class: `story story--${variant}${readIds.has(s.id) ? ' is-read' : ''}`,
      href: s.link,
      target: '_blank',
      rel: 'noopener noreferrer',
    });

    if (variant !== 'compact' && isHttp(s.image)) {
      const img = el('img', { src: s.image, alt: '', loading: variant === 'lead' ? 'eager' : 'lazy', decoding: 'async', referrerpolicy: 'no-referrer' });
      const fig = el('figure', { class: 'story__media' }, img);
      img.addEventListener('error', () => fig.remove(), { once: true });
      a.append(fig);
    }

    const section = showSection && state.day.categories.find((c) => c.id === s.categories[0]);
    const meta = el('div', { class: 'story__meta' },
      el('span', { class: 'story__source', text: s.source }),
      s.published ? el('span', { class: 'dot' }) : null,
      s.published ? el('time', { datetime: s.published, title: new Date(s.published).toLocaleString(), text: storyTime(s.published) }) : null,
      section ? el('span', { class: 'badge badge--section', text: section.label }) : null,
      isNew ? el('span', { class: 'badge', text: 'New' }) : null,
    );

    const body = el('div', { class: 'story__body' },
      meta,
      el(variant === 'lead' ? 'h2' : 'h3', { class: 'story__title', text: s.title }),
      s.summary ? el('p', { class: 'story__summary', text: s.summary }) : null,
    );
    a.append(body);

    const onOpen = () => markRead(s.id, a);
    a.addEventListener('click', onOpen);
    a.addEventListener('auxclick', (e) => { if (e.button === 1) onOpen(); });
    return a;
  }

  function renderHeader() {
    const { index, day } = state;
    const isLatest = state.date === index.latest;
    const label = dayLabel(day.date, 'long');
    const full = parseDate(day.date).toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
    els.dateline.textContent = label === 'Today' || label === 'Yesterday' ? `${label}, ${full.replace(/^[^,]+,\s*/, '')}` : full;
    document.title = isLatest ? 'Daily Digest' : `${full} · Daily Digest`;

    els.meta.replaceChildren();
    if (!isLatest) els.meta.append(el('span', { class: 'pill', text: 'Archive' }));
    const bits = [
      `${isLatest ? 'Updated' : 'Last updated'} ${isLatest ? relativeTime(day.updatedAt) : new Date(day.updatedAt).toLocaleString(undefined, { hour: 'numeric', minute: '2-digit', month: 'short', day: 'numeric' })}`,
      `${day.stories.length} stories`,
      `${day.sources.length} sources`,
    ];
    els.meta.append(bits.join(' · '));
    const failed = isLatest ? index.lastRun?.failed ?? [] : [];
    if (failed.length) {
      const names = [...new Set(failed.map((f) => f.source))].join(', ');
      els.meta.append(el('span', { title: `Unavailable on the last refresh: ${names}`, text: ` · ${failed.length} feed${failed.length === 1 ? '' : 's'} unavailable` }));
    }

    els.sources.textContent = day.sources.length ? `Sources: ${day.sources.join(', ')}.` : '';
  }

  function renderDayPicker() {
    const days = state.index.days;
    els.day.replaceChildren(...days.map((d) => el('option', {
      value: d.date,
      selected: d.date === state.date,
      text: `${dayLabel(d.date)}${d.count ? ` · ${d.count}` : ''}`,
    })));
    const i = days.findIndex((d) => d.date === state.date);
    els.newer.disabled = i <= 0;
    els.older.disabled = i === -1 || i >= days.length - 1;
  }

  function renderTabs() {
    const counts = {};
    for (const s of state.day.stories) for (const c of s.categories) counts[c] = (counts[c] || 0) + 1;
    const cats = state.day.categories.filter((c) => counts[c.id] || c.id === state.cat);
    els.tabs.replaceChildren(...cats.map((c) => {
      const btn = el('button', {
        type: 'button',
        class: 'tab',
        role: 'tab',
        'aria-selected': String(c.id === state.cat && !state.q),
        'data-cat': c.id,
      }, c.label, el('span', { class: 'count', text: String(counts[c.id] || 0) }));
      btn.addEventListener('click', () => {
        state.cat = c.id;
        if (state.q) { state.q = ''; els.q.value = ''; }
        writeHash();
        render();
        window.scrollTo({ top: Math.min(window.scrollY, els.tabs.closest('.tabs').offsetTop), behavior: 'smooth' });
      });
      return btn;
    }));
    els.tabs.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }

  function visibleStories() {
    const q = state.q.trim().toLowerCase();
    let list = state.day.stories;
    if (q) {
      const terms = q.split(/\s+/);
      list = list.filter((s) => {
        const hay = `${s.title} ${s.summary} ${s.source}`.toLowerCase();
        return terms.every((t) => hay.includes(t));
      });
    } else {
      list = list.filter((s) => s.categories.includes(state.cat));
    }
    if (state.hideRead) list = list.filter((s) => !readIds.has(s.id));
    return list;
  }

  function renderStories() {
    const list = visibleStories();
    const searching = Boolean(state.q.trim());
    els.lead.replaceChildren();
    els.grid.replaceChildren();
    els.empty.hidden = true;
    els.notice.hidden = true;

    if (searching) {
      els.notice.hidden = false;
      els.notice.textContent = `${list.length} ${list.length === 1 ? 'story matches' : 'stories match'} “${state.q.trim()}” across all sections.`;
    }

    if (!list.length) {
      const catLabel = state.day.categories.find((c) => c.id === state.cat)?.label ?? 'this section';
      showEmpty(
        searching ? 'No matches' : state.hideRead ? 'You’re all caught up' : 'Nothing here yet',
        searching
          ? 'Try a different word, or clear the search to browse by section.'
          : state.hideRead
            ? `You’ve read every story in ${catLabel}. Turn off “Hide stories I’ve read” to see them again.`
            : `No ${catLabel} stories were collected for this day.`,
      );
      els.moreHeading.hidden = true;
      return;
    }

    let rest = list;
    if (!searching && list.length > 2) {
      const leadIdx = Math.max(0, list.slice(0, 6).findIndex((s) => isHttp(s.image)));
      const lead = list[leadIdx];
      const others = list.filter((_, i) => i !== leadIdx);
      const side = others.slice(0, LEAD_SIDE_COUNT);
      rest = others.slice(LEAD_SIDE_COUNT);
      els.lead.append(
        storyNode(lead, 'lead'),
        el('div', { class: 'also' },
          el('h2', { text: state.date === state.index.latest ? 'Also today' : 'More headlines' }),
          el('ol', {}, side.map((s) => el('li', {}, storyNode(s, 'compact'))))),
      );
    }
    els.moreHeading.hidden = searching || !rest.length || !els.lead.childElementCount;
    els.lead.classList.toggle('lead--alone', !rest.length);
    els.grid.append(...rest.map((s) => storyNode(s, 'card', { showSection: searching })));
  }

  function showEmpty(title, message, code) {
    els.empty.hidden = false;
    els.empty.replaceChildren(
      el('h2', { text: title }),
      el('p', {}, message, code ? el('code', { text: code }) : null),
    );
  }

  function render() {
    renderHeader();
    renderDayPicker();
    renderTabs();
    renderStories();
  }

  // ---------------------------------------------------------------- data

  async function loadDay(date) {
    const known = state.index.days.some((d) => d.date === date);
    const target = known ? date : state.index.latest;
    const day = await getJson(`data/${target}.json`);
    state.date = target;
    state.day = day;
    if (!day.categories.some((c) => c.id === state.cat)) state.cat = day.categories[0]?.id ?? 'top';
    writeHash();
    render();
  }

  async function goTo(date) {
    try {
      await loadDay(date);
      window.scrollTo({ top: 0 });
    } catch (err) {
      console.error(err);
    }
  }

  async function checkForUpdates() {
    if (document.hidden || !state.index) return;
    try {
      const index = await getJson('data/index.json');
      if (index.updatedAt === state.index.updatedAt) {
        if (state.day) renderHeader(); // keep "Updated x ago" fresh
        return;
      }
      const wasLatest = state.date === state.index.latest;
      state.index = index;
      if (wasLatest) await loadDay(index.latest);
      else renderDayPicker();
    } catch (err) {
      console.warn('Refresh failed', err);
    }
  }

  // ---------------------------------------------------------------- wiring

  function bind() {
    els.hideRead.checked = state.hideRead;
    els.hideRead.addEventListener('change', () => {
      state.hideRead = els.hideRead.checked;
      store.set('dd.hideRead', state.hideRead);
      if (state.day) renderStories();
    });

    let timer;
    els.q.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        state.q = els.q.value;
        if (state.day) { renderTabs(); renderStories(); }
      }, 120);
    });

    els.day.addEventListener('change', () => goTo(els.day.value));
    els.older.addEventListener('click', () => step(1));
    els.newer.addEventListener('click', () => step(-1));

    document.addEventListener('keydown', (e) => {
      const typing = /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement?.tagName);
      if (e.key === '/' && !typing) {
        e.preventDefault();
        els.q.focus();
      } else if (e.key === 'Escape' && document.activeElement === els.q) {
        els.q.value = '';
        els.q.dispatchEvent(new Event('input'));
        els.q.blur();
      }
    });

    window.addEventListener('hashchange', () => {
      if (!state.index) return;
      const { date, cat } = readHash();
      if (cat) state.cat = cat;
      const wanted = date || state.index.latest;
      if (wanted !== state.date) goTo(wanted);
      else render();
    });

    document.addEventListener('visibilitychange', () => { if (!document.hidden) checkForUpdates(); });
  }

  function step(delta) {
    const days = state.index.days;
    const i = days.findIndex((d) => d.date === state.date);
    const next = days[i + delta];
    if (next) goTo(next.date);
  }

  async function init() {
    bind();
    try {
      state.index = await getJson('data/index.json');
    } catch {
      els.dateline.textContent = 'No news yet';
      els.meta.textContent = '';
      showEmpty('No news has been collected yet', 'Run this in the project folder to pull today’s headlines: ', 'npm start');
      return;
    }
    if (!state.index.days?.length) {
      showEmpty('No news has been collected yet', 'The next refresh will fill this page.');
      return;
    }
    const { date, cat } = readHash();
    if (cat) state.cat = cat;
    try {
      await loadDay(date || state.index.latest);
    } catch (err) {
      console.error(err);
      showEmpty('Couldn’t load the news', 'The news file for this day is missing or unreadable. Try another day.');
    }
    setInterval(checkForUpdates, REFRESH_MS);
  }

  init();
})();
