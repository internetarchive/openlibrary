// @ts-check
import { BarController, BarElement, CategoryScale, Chart, LinearScale, Tooltip } from 'chart.js';
import { bucketize } from './tasks_stats.js';

Chart.register(BarController, BarElement, CategoryScale, LinearScale, Tooltip);

// Slots per bar: the data comes per hour for the hour grouping, per day otherwise.
const BUCKET_SLOTS = { hour: 1, day: 1, week: 7, month: 28 };
// Longest range offered per hour; longer ranges switch back to days.
const MAX_HOURLY_DAYS = 28;

/**
 * @typedef {object} Counts
 * @property {string[]} dates ISO dates, oldest first, ending today
 * @property {number[]} humans
 * @property {number[]} bots
 * @property {Record<string, number[]>} kinds per change kind
 * @property {Record<string, number[]>} bot_kinds the part of `kinds` made by bots
 */

/**
 * @typedef {object} Walk a newest-first search through the changes for one query and filters, a page at a time
 * @property {{query: string, regex: boolean, matchCase: boolean, bot: string, kinds: string[]}} search what it looks for: `bot` is any, humans or bots, `kinds` empty for any
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
    const legend = /** @type {HTMLElement} */ (root.querySelector('.tasks-stats__parts'));
    const colorBy = /** @type {HTMLElement & {items: {value: string, label: string}[]}} */ (root.querySelector('.recentchanges-chart__color'));
    const colorTrigger = /** @type {HTMLElement} */ (colorBy.querySelector('[slot="trigger"]'));
    const queryRow = /** @type {HTMLElement} */ (root.querySelector('.recentchanges-chart__query-row'));
    const queryForm = /** @type {HTMLFormElement} */ (root.querySelector('.recentchanges-chart__query'));
    const botFilter = /** @type {HTMLElement} */ (root.querySelector('.recentchanges-chart__bot-filter'));
    const kindFilter = /** @type {HTMLElement & {items: {value: string, label: string}[]}} */ (root.querySelector('.recentchanges-chart__kind-filter'));
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
    const hourFormat = new Intl.DateTimeFormat(lang, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: 'UTC' });
    const fullHourFormat = new Intl.DateTimeFormat(lang, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hourCycle: 'h23',
        timeZone: 'UTC',
        timeZoneName: 'short'
    });
    const numberFormat = new Intl.NumberFormat(lang, { maximumFractionDigits: 0 });

    const state = {
        days: 28,
        granularity: /** @type {keyof BUCKET_SLOTS} */ ('day'),
        colorBy: 'none',
        query: '',
        regex: false,
        matchCase: false,
        bot: 'any',
        kinds: /** @type {string[]} */ ([]),
        isolated: /** @type {string | null} */ (null)
    };
    /** @type {Map<string, Promise<Counts>>} fetched once per range and unit */
    const fetched = new Map();
    // Draws await fetches, so a slow one can finish after a newer one; only the newest may paint.
    let drawId = 0;
    /** @type {Map<string, Walk>} by search, kept so returning to a search or widening the range resumes its walk */
    const walks = new Map();
    let pageSize = 200;

    /** The first ISO date in the chosen range. */
    const rangeStart = () => {
        const day = new Date();
        day.setUTCDate(day.getUTCDate() - state.days + 1);
        return day.toISOString().slice(0, 10);
    };

    /** The walk for the current search, or null without one. */
    function currentWalk() {
        if (state.colorBy !== 'query' || !state.query) return null;
        const search = { query: state.query, regex: state.regex, matchCase: state.matchCase, bot: state.bot, kinds: kind ? [kind] : [...state.kinds].sort() };
        const key = JSON.stringify(search);
        let walk = walks.get(key);
        if (!walk) {
            walk = { search, counts: {}, checked: {}, cursor: null, oldest: null, scanned: 0, done: false, running: false, stopped: false, error: '' };
            walks.set(key, walk);
        }
        return walk;
    }

    /** Pause the current walk, before the search or its filters change. */
    function stopWalk() {
        const walk = currentWalk();
        if (walk) walk.stopped = true;
    }

    /**
     * Offer every kind in the range, busiest first, in the kind filter.
     * @param {Counts} data
     */
    function updateKindFilter(data) {
        if (kind) return;
        const sum = (/** @type {number[]} */ daily) => daily.reduce((a, b) => a + b, 0);
        const kindLabels = strings.kinds || {};
        const names = [...new Set([...Object.keys(data.kinds), ...Object.keys(kindLabels)])].sort(
            (a, b) => sum(data.kinds[b] || []) - sum(data.kinds[a] || [])
        );
        const items = names.map(name => ({ value: name, label: kindLabels[name] || name }));
        if (JSON.stringify(items) !== JSON.stringify(kindFilter.items)) kindFilter.items = items;
    }

    /** @param {Walk} walk */
    const covered = walk => walk.done || (walk.oldest !== null && walk.oldest < rangeStart());

    /**
     * Fetch older pages of a walk until it covers the chosen range or is stopped, redrawing after each.
     * @param {Walk} walk
     */
    async function runWalk(walk) {
        if (walk.running) return;
        walk.running = true;
        walk.error = '';
        try {
            while (!walk.stopped && !covered(walk)) {
                const params = new URLSearchParams({ q: walk.search.query, limit: String(pageSize) });
                for (const name of walk.search.kinds) params.append('kind', name);
                if (walk.search.regex) params.set('regex', 'true');
                if (walk.search.matchCase) params.set('case', 'true');
                if (walk.search.bot !== 'any') params.set('bot', String(walk.search.bot === 'bots'));
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
                if (currentWalk() === walk) draw({ animate: false });
            }
        } catch (error) {
            walk.error = /** @type {Error} */ (error).message;
        } finally {
            walk.running = false;
            if (currentWalk() === walk) draw({ animate: false });
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

    /**
     * @param {number} days
     * @param {'day' | 'hour'} unit
     */
    function load(days, unit) {
        const key = `${days}/${unit}`;
        if (!fetched.has(key)) {
            const params = new URLSearchParams({ days: String(days), unit });
            if (kind) params.set('kind', kind);
            fetched.set(
                key,
                fetch(`/stats/recentchanges.json?${params}`).then(response => {
                    if (!response.ok) throw new Error(`HTTP ${response.status}`);
                    return response.json();
                })
            );
        }
        return /** @type {Promise<Counts>} */ (fetched.get(key));
    }

    /** @param {{animate?: boolean}} [options] animation off for redraws as a walk's pages arrive, which would otherwise restart it every page */
    async function draw({ animate = true } = {}) {
        const id = ++drawId;
        const unit = state.granularity === 'hour' ? 'hour' : 'day';
        /** @type {Counts} */
        let data;
        try {
            data = await load(state.days, unit);
            if (id !== drawId) return;
        } catch {
            fetched.delete(`${state.days}/${unit}`);
            const error = document.createElement('p');
            error.className = 'tasks-stats__error';
            error.textContent = strings.loadFailed;
            canvas.parentElement?.replaceChildren(error);
            return;
        }
        // Slots are `YYYY-MM-DD` or, per hour, `YYYY-MM-DDTHH`, in UTC
        const dates = data.dates.map(d => new Date(unit === 'hour' ? `${d}:00:00Z` : `${d}T00:00:00Z`));
        const lastDay = dates.length - 1;
        const size = BUCKET_SLOTS[state.granularity];
        // Rounded down, so the chart never reaches back further than the chosen range.
        const count = Math.max(1, Math.floor(dates.length / size));
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
        } else if (currentWalk()) {
            const walk = /** @type {Walk} */ (currentWalk());
            if (!walk.stopped && !walk.error && !covered(walk)) runWalk(walk);
            // Only the changes the filters let through, so those it skips don't read as not searched yet
            const zeros = data.dates.map(() => 0);
            const kinds = walk.search.kinds;
            const sumOf = (/** @type {Record<string, number[]>} */ byKind) => zeros.map((_, i) => kinds.reduce((n, name) => n + (byKind[name]?.[i] || 0), 0));
            const all = kinds.length ? sumOf(data.kinds) : total;
            const bots = kinds.length ? sumOf(data.bot_kinds) : data.bots;
            const filtered = walk.search.bot === 'bots' ? bots : walk.search.bot === 'humans' ? all.map((n, i) => n - bots[i]) : all;
            // The walk counts per hour; per day, sum each day's hours
            const perSlot = (/** @type {Record<string, number>} */ byHour) => {
                if (unit === 'hour') return byHour;
                /** @type {Record<string, number>} */
                const byDay = {};
                for (const [hour, n] of Object.entries(byHour)) byDay[hour.slice(0, 10)] = (byDay[hour.slice(0, 10)] || 0) + n;
                return byDay;
            };
            const counts = perSlot(walk.counts);
            const checkedBySlot = perSlot(walk.checked);
            const matching = data.dates.map(slot => counts[slot] || 0);
            // The daily totals are cached, so a day's changes checked can run past its total
            const checked = data.dates.map((slot, i) => Math.min(checkedBySlot[slot] || 0, filtered[i]));
            parts = [
                { label: fill(strings.matches, { text: state.regex ? `/${state.query}/` : state.query }), color: colors.match, daily: matching },
                { label: strings.nonMatches, color: colors.muted, daily: checked.map((n, i) => Math.max(0, n - matching[i])) },
                { label: strings.notSearched, color: colors.unsearched, daily: filtered.map((n, i) => n - checked[i]) }
            ];
        } else {
            parts = [{ label: '', color: colors.bar, daily: total }];
        }
        showWalkStatus(currentWalk());
        updateKindFilter(data);
        const stacked = parts.length > 1;
        // The legend item clicked to show only its series; kept across redraws while that series is still charted
        const isolated = stacked && parts.some(part => part.label === state.isolated) ? state.isolated : null;
        const totals = bucketize(total, size).slice(-count);

        /** @param {import('./tasks_stats.js').Bucket} b */
        const shortLabel = b =>
            unit === 'hour'
                ? hourFormat.format(dates[b.end])
                : b.start === b.end
                  ? dayFormat.format(dates[b.end])
                  : `${dayFormat.format(dates[b.start])} – ${dayFormat.format(dates[b.end])}`;
        /** @param {import('./tasks_stats.js').Bucket} b */
        const fullLabel = b =>
            unit === 'hour'
                ? fullHourFormat.format(dates[b.end])
                : b.start === b.end
                  ? fullFormat.format(dates[b.end])
                  : `${fullFormat.format(dates[b.start])} – ${fullFormat.format(dates[b.end])}`;
        /** @param {import('./tasks_stats.js').Bucket} b */
        const inProgressNote = b =>
            b.end !== lastDay ? '' : unit === 'hour' ? strings.hourSoFar : b.start === b.end ? strings.todaySoFar : strings.periodSoFar;

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
                stack: 'parts',
                hidden: isolated !== null && part.label !== isolated
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
                                const lines = stacked && isolated === null ? [fill(strings.total, { count: numberFormat.format(bucket.value ?? 0) })] : [];
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
                const item = document.createElement('button');
                item.type = 'button';
                item.className = 'tasks-stats__part recentchanges-chart__part';
                item.classList.toggle('recentchanges-chart__part--hidden', isolated !== null && part.label !== isolated);
                item.setAttribute('aria-pressed', String(part.label === isolated));
                item.style.setProperty('--swatch', part.color);
                item.textContent = part.label;
                item.addEventListener('mouseenter', () => focus(i));
                item.addEventListener('mouseleave', () => focus(null));
                item.addEventListener('focus', () => focus(i));
                item.addEventListener('blur', () => focus(null));
                // Show only this series; again to show them all
                item.addEventListener('click', () => {
                    state.isolated = part.label === isolated ? null : part.label;
                    draw().then(() => /** @type {HTMLElement | undefined} */ (legend.children[i])?.focus());
                });
                return item;
            })
        );
    }

    const rangeControl = /** @type {HTMLElement & {value: string}} */ (root.querySelector('.recentchanges-chart__range'));
    const granularityControl = /** @type {HTMLElement & {value: string}} */ (root.querySelector('.recentchanges-chart__granularity'));
    // Hourly bars are kept to MAX_HOURLY_DAYS, so each control gives way to the other rather than draw thousands of bars
    rangeControl.addEventListener('ol-segmented-control-change', event => {
        state.days = Number(/** @type {CustomEvent} */ (event).detail.value);
        if (state.granularity === 'hour' && state.days > MAX_HOURLY_DAYS) {
            state.granularity = 'day';
            granularityControl.value = 'day';
        }
        draw();
    });
    granularityControl.addEventListener('ol-segmented-control-change', event => {
        state.granularity = /** @type {CustomEvent} */ (event).detail.value;
        if (state.granularity === 'hour' && state.days > MAX_HOURLY_DAYS) {
            state.days = MAX_HOURLY_DAYS;
            rangeControl.value = String(MAX_HOURLY_DAYS);
        }
        draw();
    });
    colorBy.addEventListener('ol-options-popover-change', event => {
        const selected = /** @type {CustomEvent} */ (event).detail.selected || 'none';
        const choice = colorBy.items.find(item => item.value === selected);
        colorTrigger.textContent = fill(strings.colorBy, { choice: choice?.label || '' });
        stopWalk();
        state.colorBy = selected;
        queryRow.hidden = state.colorBy !== 'query';
        const walk = currentWalk();
        if (walk) walk.stopped = false;
        draw();
    });
    queryForm.addEventListener('submit', event => {
        event.preventDefault();
        stopWalk();
        state.query = queryInput.value.trim();
        const walk = currentWalk();
        if (walk) walk.stopped = false;
        draw();
    });
    /** Start the walk for the search as it now stands, after a filter changed. */
    function restartWalk() {
        const walk = currentWalk();
        if (walk) walk.stopped = false;
        draw();
    }
    botFilter.addEventListener('ol-options-popover-change', event => {
        const value = /** @type {CustomEvent} */ (event).detail.selected || 'any';
        stopWalk();
        state.bot = value;
        const choice = /** @type {{value: string, label: string}[]} */ (/** @type {any} */ (botFilter).items || []).find(item => item.value === value);
        /** @type {HTMLElement} */ (botFilter.querySelector('[slot="trigger"]')).textContent = fill(strings.botFilter, { choice: choice?.label || '' });
        restartWalk();
    });
    kindFilter.addEventListener('ol-select-popover-change', event => {
        stopWalk();
        state.kinds = [.../** @type {CustomEvent} */ (event).detail.selected];
        const labelFor = (/** @type {string} */ value) => kindFilter.items.find(item => item.value === value)?.label || value;
        const count = state.kinds.length;
        const choice = count === 0 ? strings.any : count === 1 ? labelFor(state.kinds[0]) : fill(strings.kindCount, { count: String(count) });
        const trigger = /** @type {HTMLElement} */ (kindFilter.querySelector('[slot="trigger"]'));
        trigger.textContent = fill(strings.kindFilter, { choice });
        // Tinted while filtering, as ol-select-popover's own trigger is
        trigger.toggleAttribute('selected', count > 0);
        restartWalk();
    });
    /** @type {NodeListOf<HTMLButtonElement>} */ (root.querySelectorAll('.recentchanges-chart__search-toggle')).forEach(toggle => {
        toggle.addEventListener('click', () => {
            const on = toggle.getAttribute('aria-pressed') !== 'true';
            toggle.setAttribute('aria-pressed', String(on));
            stopWalk();
            if (toggle.classList.contains('recentchanges-chart__regex')) state.regex = on;
            else state.matchCase = on;
            restartWalk();
        });
    });
    walkToggle.addEventListener('click', () => {
        const walk = currentWalk();
        if (!walk) return;
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
