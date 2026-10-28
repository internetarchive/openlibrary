/**
 * The public /tasks page's "happening now" feed.
 *
 * Rows arrive at the top one at a time, each stamped with the current time.
 * They walk a rotation from /tasks/feed.json, a cached pool of real edits.
 * Markup mirrors the ``feed_row`` macro in macros/contribute/parts.html.jinja.
 */

const MAX_ROWS = 25;
const GAP_MS = [3500, 7000];
// How long to wait before asking again when there are no edits to show.
const EMPTY_RETRY_MS = 60000;
// While placeholder rows are up, the server is building the feed in the background: ask again soon, a few
// times, and fill the placeholders quickly once rows arrive. After that many tries, say the feed is quiet.
const SKELETON_RETRY_MS = 5000;
const SKELETON_MAX_TRIES = 12;
const SKELETON_FILL_GAP_MS = 500;
const RELATIVE_REFRESH_MS = 30000;

// Short units ("12 min. ago") so the time fits the ledger's margin column.
const relativeTime = new Intl.RelativeTimeFormat(document.documentElement.lang || 'en', { numeric: 'auto', style: 'short' });

/**
 * "now", "3 minutes ago", … from an ISO timestamp.
 * @param {string} iso
 * @returns {string}
 */
export function formatWhen(iso) {
    const ago = Math.round((Date.now() - new Date(iso)) / 1000);
    if (ago < 45) return relativeTime.format(0, 'second');
    if (ago < 3600) return relativeTime.format(-Math.round(ago / 60), 'minute');
    if (ago < 86400) return relativeTime.format(-Math.round(ago / 3600), 'hour');
    return relativeTime.format(-Math.round(ago / 86400), 'day');
}

/**
 * Build one feed row. Text goes in via textContent, never HTML.
 * @param {object} row - a row from /tasks/feed.json
 * @param {string} byTemplate - the translated "by %(authors)s"
 * @returns {HTMLLIElement}
 */
function buildRow(row, byTemplate) {
    const el = (tag, className, text) => {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    };

    const li = el('li', 'contrib-feed__row');
    li.dataset.feedRow = '';
    const inner = el('div', 'contrib-feed__inner');

    const when = el('time', 'contrib-feed__when', formatWhen(row.timestamp));
    when.dateTime = row.timestamp;
    when.dataset.feedWhen = '';

    const cover = el('a', 'contrib-feed__cover');
    cover.href = row.key;
    cover.tabIndex = -1;
    cover.setAttribute('aria-hidden', 'true');
    if (row.cover_url) {
        const img = el('img');
        img.src = row.cover_url;
        img.alt = '';
        img.width = 32;
        img.height = 48;
        img.loading = 'lazy';
        cover.append(img);
    } else {
        const empty = el('span', 'contrib-feed__cover--empty');
        empty.append(el('ol-icon'));
        empty.firstChild.setAttribute('name', 'book-open');
        empty.firstChild.setAttribute('size', 'sm');
        cover.append(empty);
    }

    const title = el('div', 'contrib-feed__title');
    const link = el('a', 'contrib-feed__link', row.title);
    link.href = row.key;
    title.append(link);
    if (row.authors) title.append(' ', el('span', 'contrib-feed__by', byTemplate.replace('%(authors)s', row.authors)));

    const line = el('div', 'contrib-feed__line');
    line.append(el('span', 'contrib-feed__editor', row.editor), ' ', el('span', undefined, row.comment || row.action));

    const meta = el('div', 'contrib-feed__meta');
    meta.append(title, line);

    inner.append(when, cover, meta);
    li.append(inner);
    return li;
}

/**
 * Prepend a row with the enter animation, mark it as the newest, and trim the list from the bottom.
 * @param {HTMLOListElement} list
 * @param {object} row
 */
function insertRow(list, row) {
    const li = buildRow(row, list.dataset.feedBy || 'by %(authors)s');
    list.querySelectorAll('.is-new').forEach(prev => prev.classList.remove('is-new'));
    li.classList.add('is-entering', 'is-new');
    list.prepend(li);
    // Each real row takes a placeholder's place, from the bottom, so the list keeps its height.
    const skeletons = skeletonRows(list);
    skeletons[skeletons.length - 1]?.remove();
    // Two frames so the entering styles are painted before they transition away.
    requestAnimationFrame(() => requestAnimationFrame(() => li.classList.remove('is-entering')));
    list.closest('section')?.querySelector('[data-feed-empty]')?.setAttribute('hidden', '');

    const rows = list.querySelectorAll('[data-feed-row]:not(.is-leaving)');
    for (let i = MAX_ROWS; i < rows.length; i++) {
        const extra = rows[i];
        extra.classList.add('is-leaving');
        const ms = parseFloat(getComputedStyle(extra).transitionDuration) * 1000;
        setTimeout(() => extra.remove(), ms || 0);
    }
}

/**
 * The placeholder rows still waiting on a real one.
 * @param {HTMLOListElement} list
 * @returns {HTMLLIElement[]}
 */
function skeletonRows(list) {
    return [...list.querySelectorAll('[data-feed-skeleton]')];
}

/**
 * Stop waiting: drop the placeholders and, with no rows at all, say the feed is quiet.
 * @param {HTMLOListElement} list
 */
function showEmpty(list) {
    skeletonRows(list).forEach(li => li.remove());
    if (!list.querySelector('[data-feed-row]')) {
        list.closest('section')?.querySelector('[data-feed-empty]')?.removeAttribute('hidden');
    }
}

/**
 * Refresh every row's relative time.
 * @param {HTMLOListElement} list
 */
function refreshTimes(list) {
    list.querySelectorAll('[data-feed-when]').forEach(el => {
        el.textContent = formatWhen(el.dateTime);
    });
}

/**
 * Wire the feed list: rotate through recent edits and keep rows coming while the tab is visible.
 * @param {HTMLOListElement} list - the ``[data-feed]`` element
 * @returns {void}
 */
export function initFeed(list) {
    const url = list.dataset.feedUrl;
    let cursor = list.dataset.feedCursor || '';
    const queue = [];
    let revealTimer = null;
    let emptyTries = 0;

    const fetchRows = async params => {
        try {
            const res = await fetch(`${url}?${new URLSearchParams({ limit: '20', ...params })}`);
            if (!res.ok) return [];
            return (await res.json()).rows || [];
        } catch (e) {
            return [];
        }
    };

    const showNext = () => {
        const row = queue.shift();
        if (row) insertRow(list, row);
    };

    // Walk the rotation forever, one row every few seconds, each stamped "now".
    const tick = async () => {
        if (queue.length < 5) {
            const rows = await fetchRows({ offset: cursor });
            cursor = String(Number(cursor) + rows.length);
            rows.reverse().forEach(r => queue.push({ ...r, timestamp: new Date().toISOString() }));
        }
        if (document.hidden) return;
        if (!queue.length) {
            const waiting = skeletonRows(list).length && ++emptyTries < SKELETON_MAX_TRIES;
            if (!waiting) showEmpty(list);
            revealTimer = setTimeout(tick, waiting ? SKELETON_RETRY_MS : EMPTY_RETRY_MS);
            return;
        }
        showNext();
        const gap = skeletonRows(list).length ? SKELETON_FILL_GAP_MS : GAP_MS[0] + Math.random() * (GAP_MS[1] - GAP_MS[0]);
        revealTimer = setTimeout(tick, gap);
    };

    const stop = () => clearTimeout(revealTimer);
    const start = () => {
        stop();
        tick();
    };

    document.addEventListener('visibilitychange', () => (document.hidden ? stop() : start()));
    setInterval(() => refreshTimes(list), RELATIVE_REFRESH_MS);
    refreshTimes(list);
    if (!document.hidden) start();
}
