// @ts-check
import { BarController, BarElement, CategoryScale, Chart, LinearScale, Tooltip } from 'chart.js';
import { bucketize } from './tasks_stats.js';

Chart.register(BarController, BarElement, CategoryScale, LinearScale, Tooltip);

const BUCKET_DAYS = { day: 1, week: 7, month: 28 };

/**
 * @typedef {object} Counts
 * @property {string[]} dates ISO dates, oldest first, ending today
 * @property {number[]} humans
 * @property {number[]} bots
 * @property {Record<string, number[]>} kinds per change kind
 */

/**
 * @typedef {object} Walk a newest-first search through the changes for one query, a page at a time
 * @property {Record<string, number>} counts matching changes per ISO date
 * @property {Record<string, number>} checked changes checked per ISO date
 * @property {number | null} cursor `before` for the next page
 * @property {string | null} oldest ISO date of the oldest change checked so far; every day after it is fully covered
 * @property {number} scanned changes checked
 * @property {boolean} done no older changes are left
 * @property {boolean} running a page is in flight
 * @property {boolean} stopped stopped by the patron
 * @property {string} error why the last page failed
 */

// More legend items than this and the tooltip shows only the hovered segment.
const MAX_TOOLTIP_PARTS = 5;

// Page sizes for the walk, in changes; it aims for pages of a second or two.
const MIN_PAGE = 10;
const MAX_PAGE = 5000;

/**
 * @param {string} template
 * @param {Record<string, string>} values
 */
function fill(template, values) {
    return template.replace(/%\((\w+)\)s/g, (match, name) => values[name] ?? match);
}

/**
 * The changes-per-period bar chart on /recentchanges and its per-kind pages, styled and behaving like the main chart
 * on /stats/tasks (tasks_stats.js).
 * @param {HTMLElement} root the `.recentchanges-chart` section
 */
export function init(root) {
    const strings = JSON.parse(root.dataset.i18n || '{}');
    const kind = root.dataset.kind || '';
    const canvas = /** @type {HTMLCanvasElement} */ (root.querySelector('canvas'));
    const unit = /** @type {HTMLElement} */ (root.querySelector('.tasks-stats__chart-unit'));
    const legend = /** @type {HTMLElement} */ (root.querySelector('.tasks-stats__parts'));
    const colorBy = /** @type {HTMLElement & {items: {value: string, label: string}[]}} */ (root.querySelector('.recentchanges-chart__color'));
    const colorTrigger = /** @type {HTMLElement} */ (colorBy.querySelector('[slot="trigger"]'));
    const queryForm = /** @type {HTMLFormElement} */ (root.querySelector('.recentchanges-chart__query'));
    const queryInput = /** @type {HTMLInputElement} */ (queryForm.querySelector('input'));
    const status = /** @type {HTMLElement} */ (root.querySelector('.recentchanges-chart__status'));
    const statusText = /** @type {HTMLElement} */ (status.querySelector('.recentchanges-chart__status-text'));
    const walkToggle = /** @type {HTMLElement} */ (status.querySelector('.recentchanges-chart__walk-toggle'));

    const style = getComputedStyle(root);
    const token = (/** @type {string} */ name) => style.getPropertyValue(name).trim();
    const colors = {
        bar: resolveColor(root, 'var(--color-stats-chart-bar)'),
        accent: resolveColor(root, 'var(--color-stats-chart-accent)'),
        muted: resolveColor(root, 'var(--color-stats-chart-muted)'),
        match: resolveColor(root, 'var(--color-chart-4)'),
        unsearched: resolveColor(root, 'var(--color-border-subtle)'),
        // One hue per kind, in order of size; reused from the top past the last
        kinds: [
            '--color-stats-chart-bar',
            '--color-stats-chart-accent',
            '--color-chart-2',
            '--color-chart-4',
            '--color-chart-bar',
            '--color-stats-chart-muted',
            '--blue-700',
            '--green-700',
            '--red-700',
            '--pink-600'
        ].map(name => resolveColor(root, `var(${name})`)),
        secondary: resolveColor(root, 'var(--color-text-secondary)'),
        text: resolveColor(root, 'var(--color-text)'),
        grid: token('--color-border-subtle'),
        surface: token('--color-surface')
    };
    Chart.defaults.font.family = token('--font-family-body');
    Chart.defaults.font.size = parseInt(token('--font-size-body-small'));
    Chart.defaults.color = colors.secondary;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) Chart.defaults.animation = false;

    const lang = document.documentElement.lang || undefined;
    const dayFormat = new Intl.DateTimeFormat(lang, { month: 'short', day: 'numeric', timeZone: 'UTC' });
    const fullFormat = new Intl.DateTimeFormat(lang, { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' });
    const numberFormat = new Intl.NumberFormat(lang, { maximumFractionDigits: 0 });
    const units = { day: strings.perDay, week: strings.perWeek, month: strings.perMonth };

    const state = { days: 28, granularity: /** @type {keyof BUCKET_DAYS} */ ('day'), colorBy: 'none', query: '' };
    /** @type {Map<number, Promise<Counts>>} fetched once per range */
    const fetched = new Map();
    // Draws await fetches, so a slow one can finish after a newer one; only the newest may paint.
    let drawId = 0;
    /** @type {Map<string, Walk>} by query, kept so returning to a query or widening the range resumes its walk */
    const walks = new Map();
    let pageSize = 200;

    /** The first ISO date in the chosen range. */
    const rangeStart = () => {
        const day = new Date();
        day.setUTCDate(day.getUTCDate() - state.days + 1);
        return day.toISOString().slice(0, 10);
    };

    /** @param {string} query */
    function walkFor(query) {
        let walk = walks.get(query);
        if (!walk) {
            walk = { counts: {}, checked: {}, cursor: null, oldest: null, scanned: 0, done: false, running: false, stopped: false, error: '' };
            walks.set(query, walk);
        }
        return walk;
    }

    /** @param {Walk} walk */
    const covered = walk => walk.done || (walk.oldest !== null && walk.oldest < rangeStart());

    /**
     * Fetch older pages of `query`'s walk until it covers the chosen range or is stopped, redrawing after each.
     * @param {string} query
     */
    async function runWalk(query) {
        const walk = walkFor(query);
        if (walk.running) return;
        walk.running = true;
        walk.error = '';
        try {
            while (!walk.stopped && !covered(walk)) {
                const params = new URLSearchParams({ q: query, limit: String(pageSize) });
                if (kind) params.set('kind', kind);
                if (walk.cursor !== null) params.set('before', String(walk.cursor));
                const started = performance.now();
                const response = await fetch(`/stats/recentchanges/matches.json?${params}`);
                // A page that ran out of time is retried smaller
                if (response.status === 504 && pageSize > MIN_PAGE) {
                    pageSize = Math.max(MIN_PAGE, Math.floor(pageSize / 2));
                    continue;
                }
                if (!response.ok) {
                    const detail = await response.json().then(
                        body => body.detail,
                        () => null
                    );
                    throw new Error(typeof detail === 'string' ? detail : `HTTP ${response.status}`);
                }
                /** @type {{counts: Record<string, number>, checked: Record<string, number>, scanned: number, next: number | null, oldest: string | null}} */
                const page = await response.json();
                const elapsed = performance.now() - started;
                if (elapsed < 1000) pageSize = Math.min(MAX_PAGE, pageSize * 2);
                else if (elapsed > 4000) pageSize = Math.max(MIN_PAGE, Math.floor(pageSize / 2));
                for (const [day, n] of Object.entries(page.counts)) walk.counts[day] = (walk.counts[day] || 0) + n;
                for (const [day, n] of Object.entries(page.checked)) walk.checked[day] = (walk.checked[day] || 0) + n;
                walk.scanned += page.scanned;
                walk.cursor = page.next;
                walk.done = page.next === null;
                // Ids rise with time only roughly, so keep the earliest day seen
                if (page.oldest && (walk.oldest === null || page.oldest.slice(0, 10) < walk.oldest)) walk.oldest = page.oldest.slice(0, 10);
                if (state.query === query) draw({ animate: false });
            }
        } catch (error) {
            walk.error = /** @type {Error} */ (error).message;
        } finally {
            walk.running = false;
            if (state.query === query) draw({ animate: false });
        }
    }

    /** @param {Walk | null} walk */
    function showWalkStatus(walk) {
        status.hidden = !walk;
        if (!walk) return;
        const values = {
            count: numberFormat.format(walk.scanned),
            date: walk.oldest ? fullFormat.format(new Date(`${walk.oldest}T00:00:00Z`)) : '…'
        };
        let text;
        let toggle = '';
        if (walk.error) {
            text = fill(strings.searchFailed, { reason: walk.error });
            toggle = strings.resume;
        } else if (covered(walk)) {
            text = fill(strings.walkDone, values);
        } else if (walk.stopped) {
            text = fill(strings.walkStopped, values);
            toggle = strings.resume;
        } else {
            text = fill(strings.walking, values);
            toggle = strings.stop;
        }
        statusText.textContent = text;
        walkToggle.textContent = toggle;
        walkToggle.hidden = !toggle;
    }

    /** @param {number} days */
    function load(days) {
        if (!fetched.has(days)) {
            const params = new URLSearchParams({ days: String(days) });
            if (kind) params.set('kind', kind);
            fetched.set(
                days,
                fetch(`/stats/recentchanges.json?${params}`).then(response => {
                    if (!response.ok) throw new Error(`HTTP ${response.status}`);
                    return response.json();
                })
            );
        }
        return /** @type {Promise<Counts>} */ (fetched.get(days));
    }

    /** @param {{animate?: boolean}} [options] animation off for redraws as a walk's pages arrive, which would otherwise restart it every page */
    async function draw({ animate = true } = {}) {
        const id = ++drawId;
        /** @type {Counts} */
        let data;
        try {
            data = await load(state.days);
            if (id !== drawId) return;
        } catch {
            fetched.delete(state.days);
            const error = document.createElement('p');
            error.className = 'tasks-stats__error';
            error.textContent = strings.loadFailed;
            canvas.parentElement?.replaceChildren(error);
            return;
        }
        const dates = data.dates.map(d => new Date(`${d}T00:00:00Z`));
        const lastDay = dates.length - 1;
        const size = BUCKET_DAYS[state.granularity];
        // Rounded down, so the chart never reaches back further than the chosen range.
        const count = Math.max(1, Math.floor(state.days / size));
        const total = data.humans.map((n, i) => n + data.bots[i]);
        /** @type {{label: string, color: string, daily: number[]}[]} */
        let parts;
        if (state.colorBy === 'bot') {
            parts = [
                { label: strings.humans, color: colors.bar, daily: data.humans },
                { label: strings.bots, color: colors.accent, daily: data.bots }
            ];
        } else if (state.colorBy === 'kind') {
            const sum = (/** @type {number[]} */ daily) => daily.reduce((a, b) => a + b, 0);
            const ranked = Object.entries(data.kinds).sort(([, a], [, b]) => sum(b) - sum(a));
            const kindLabels = strings.kinds || {};
            parts = ranked.map(([name, daily], i) => ({ label: kindLabels[name] || name, color: colors.kinds[i % colors.kinds.length], daily }));
        } else if (state.colorBy === 'query' && state.query) {
            const walk = walkFor(state.query);
            if (!walk.stopped && !walk.error && !covered(walk)) runWalk(state.query);
            const matching = data.dates.map(day => walk.counts[day] || 0);
            // The daily totals are cached, so a day's changes checked can run past its total
            const checked = data.dates.map((day, i) => Math.min(walk.checked[day] || 0, total[i]));
            parts = [
                { label: fill(strings.matches, { text: state.query }), color: colors.match, daily: matching },
                { label: strings.nonMatches, color: colors.muted, daily: checked.map((n, i) => Math.max(0, n - matching[i])) },
                { label: strings.notSearched, color: colors.unsearched, daily: total.map((n, i) => n - checked[i]) }
            ];
        } else {
            parts = [{ label: '', color: colors.bar, daily: total }];
        }
        showWalkStatus(state.colorBy === 'query' && state.query ? walkFor(state.query) : null);
        const stacked = parts.length > 1;
        const totals = bucketize(total, size).slice(-count);

        /** @param {import('./tasks_stats.js').Bucket} b */
        const shortLabel = b =>
            b.start === b.end ? dayFormat.format(dates[b.end]) : `${dayFormat.format(dates[b.start])} – ${dayFormat.format(dates[b.end])}`;
        /** @param {import('./tasks_stats.js').Bucket} b */
        const fullLabel = b =>
            b.start === b.end ? fullFormat.format(dates[b.end]) : `${fullFormat.format(dates[b.start])} – ${fullFormat.format(dates[b.end])}`;
        /** @param {import('./tasks_stats.js').Bucket} b */
        const inProgressNote = b => (b.end !== lastDay ? '' : b.start === b.end ? strings.todaySoFar : strings.periodSoFar);

        /**
         * Bar colours for one part. The day or period still being counted is paler, and so is every part but the one
         * whose legend item is hovered.
         * @param {{color: string}} part
         * @param {import('./tasks_stats.js').Bucket[]} buckets
         * @param {boolean} [faded]
         */
        const barColors = (part, buckets, faded = false) => buckets.map(b => withAlpha(part.color, (b.end === lastDay ? 0.45 : 1) * (faded ? 0.2 : 1)));
        const partBuckets = parts.map(part => bucketize(part.daily, size).slice(-count));
        const datasets = parts.map((part, i) => {
            const buckets = partBuckets[i];
            return {
                label: part.label,
                data: buckets.map(b => b.value),
                backgroundColor: barColors(part, buckets),
                borderRadius: stacked ? 0 : 2,
                barPercentage: buckets.length > 120 ? 1 : 0.8,
                categoryPercentage: 0.9,
                stack: 'parts'
            };
        });
        const config = {
            type: /** @type {const} */ ('bar'),
            data: { labels: totals.map(shortLabel), datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                // With many parts, a tooltip listing them all is hard to read, so it describes just the segment under the pointer
                interaction:
                    parts.length > MAX_TOOLTIP_PARTS
                        ? { mode: /** @type {const} */ ('nearest'), intersect: true }
                        : { mode: /** @type {const} */ ('index'), intersect: false },
                scales: {
                    x: { stacked, grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8 } },
                    y: { stacked, beginAtZero: true, border: { display: false }, grid: { color: colors.grid }, ticks: { precision: 0 } }
                },
                plugins: {
                    tooltip: {
                        backgroundColor: colors.surface,
                        titleColor: colors.text,
                        bodyColor: colors.text,
                        footerColor: colors.secondary,
                        borderColor: colors.grid,
                        borderWidth: 1,
                        padding: 10,
                        displayColors: false,
                        filter: (/** @type {any} */ item) => !stacked || item.raw > 0,
                        callbacks: {
                            title: (/** @type {any[]} */ items) => (items.length ? fullLabel(totals[items[0].dataIndex]) : ''),
                            label: (/** @type {any} */ item) =>
                                stacked ? `${item.dataset.label}: ${numberFormat.format(item.raw)}` : numberFormat.format(item.raw),
                            footer: (/** @type {any[]} */ items) => {
                                if (!items.length) return [];
                                const bucket = totals[items[0].dataIndex];
                                const lines = stacked ? [fill(strings.total, { count: numberFormat.format(bucket.value ?? 0) })] : [];
                                lines.push(inProgressNote(bucket));
                                return lines.filter(Boolean);
                            }
                        }
                    }
                }
            }
        };
        const existing = Chart.getChart(canvas);
        if (existing) {
            existing.data = config.data;
            existing.options = config.options;
            existing.update(animate ? undefined : 'none');
        } else {
            new Chart(canvas, config);
        }

        let empty = canvas.parentElement?.querySelector('.tasks-stats__empty');
        const hasData = total.some(Boolean);
        if (!hasData && !empty) {
            empty = document.createElement('p');
            empty.className = 'tasks-stats__note tasks-stats__empty';
            empty.textContent = strings.noData;
            canvas.parentElement?.append(empty);
        }
        if (hasData) empty?.remove();

        unit.textContent = units[state.granularity];
        /** @param {number | null} focused index of the hovered legend item, or null for none */
        const focus = focused => {
            const chart = Chart.getChart(canvas);
            if (!chart) return;
            chart.data.datasets.forEach((dataset, i) => {
                dataset.backgroundColor = barColors(parts[i], partBuckets[i], focused !== null && i !== focused);
            });
            chart.update('none');
            legend
                .querySelectorAll('.tasks-stats__part')
                .forEach((item, i) => item.classList.toggle('recentchanges-chart__part--faded', focused !== null && i !== focused));
        };
        legend.replaceChildren(
            ...(stacked ? parts : []).map((part, i) => {
                const item = document.createElement('span');
                item.className = 'tasks-stats__part';
                item.style.setProperty('--swatch', part.color);
                item.textContent = part.label;
                item.addEventListener('mouseenter', () => focus(i));
                item.addEventListener('mouseleave', () => focus(null));
                return item;
            })
        );
    }

    root.querySelector('.recentchanges-chart__range')?.addEventListener('ol-segmented-control-change', event => {
        state.days = Number(/** @type {CustomEvent} */ (event).detail.value);
        draw();
    });
    root.querySelector('.recentchanges-chart__granularity')?.addEventListener('ol-segmented-control-change', event => {
        state.granularity = /** @type {CustomEvent} */ (event).detail.value;
        draw();
    });
    colorBy.addEventListener('ol-options-popover-change', event => {
        state.colorBy = /** @type {CustomEvent} */ (event).detail.selected || 'none';
        const choice = colorBy.items.find(item => item.value === state.colorBy);
        colorTrigger.textContent = fill(strings.colorBy, { choice: choice?.label || '' });
        queryForm.hidden = state.colorBy !== 'query';
        if (state.colorBy !== 'query' && state.query) walkFor(state.query).stopped = true;
        draw();
    });
    queryForm.addEventListener('submit', event => {
        event.preventDefault();
        const query = queryInput.value.trim();
        if (state.query && state.query !== query) walkFor(state.query).stopped = true;
        state.query = query;
        const walk = walkFor(query);
        walk.stopped = false;
        draw();
    });
    walkToggle.addEventListener('click', () => {
        const walk = walkFor(state.query);
        walk.stopped = !walk.error && !walk.stopped && walk.running;
        walk.error = '';
        draw();
    });

    draw();
}

/**
 * A colour as `rgb(…)`, so it can take an alpha. Resolved through a probe so token chains and any colour syntax work.
 * @param {HTMLElement} root
 * @param {string} value
 */
function resolveColor(root, value) {
    const probe = document.createElement('span');
    probe.style.color = value;
    probe.hidden = true;
    root.append(probe);
    const color = getComputedStyle(probe).color;
    probe.remove();
    return color;
}

/**
 * @param {string} rgb an `rgb(r, g, b)` string
 * @param {number} alpha
 */
function withAlpha(rgb, alpha) {
    const [r, g, b] = rgb.match(/[\d.]+/g) || [];
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
