// @ts-check
import { BarController, BarElement, CategoryScale, Chart, Filler, LinearScale, LineController, LineElement, PointElement, Tooltip } from 'chart.js';

Chart.register(BarController, BarElement, CategoryScale, Filler, LinearScale, LineController, LineElement, PointElement, Tooltip);

/** English fallbacks; the page's `data-i18n` overrides them. Keys match build_tasks_stats_i18n in openlibrary/views/loanstats.py. */
export const DEFAULT_STRINGS = {
    perDay: 'Per day',
    perWeek: 'Per week',
    perMonth: 'Per 4 weeks',
    previousPeriod: 'Previous period',
    previousValue: 'Previous period: %(count)s',
    change: '%(change)s vs previous period',
    todaySoFar: 'Today so far, updated hourly',
    periodSoFar: 'Still in progress',
    openDetails: '%(count)s details still open',
    undoneShare: '%(share)s undone: %(undone)s of %(saves)s saves in the 28 days to this day',
    noData: 'No counts for this range yet.',
    loadFailed: "The charts couldn't load. Reload the page to try again."
};

// Enough for a 12-month range; matches MAX_DAYS in openlibrary/fastapi/stats.py.
const FETCH_DAYS = 400;
const BUCKET_DAYS = { day: 1, week: 7, month: 28 };

/**
 * What each card charts. Counts of people can't be added up across days, so week and month views of those take the stored
 * 7- or 28-day window ending on the period's last day instead.
 * @type {Record<string, {daily: string, windows?: {week: string, month: string}}>}
 */
const METRICS = {
    editors: { daily: 'catalog_editors_1d', windows: { week: 'catalog_editors_7d', month: 'catalog_editors_28d' } },
    new_editors: { daily: 'new_catalog_editors_1d' },
    saves: { daily: 'tasks_saves_1d' },
    tasks_editors: { daily: 'tasks_editors_1d', windows: { week: 'tasks_editors_7d', month: 'tasks_editors_28d' } }
};

/**
 * @typedef {object} TasksSeries
 * @property {string[]} dates ISO dates, oldest first, ending today
 * @property {Record<string, (number | null)[]>} series
 */

/**
 * @typedef {object} Bucket
 * @property {number} start index of the first day
 * @property {number} end index of the last day
 * @property {number | null} value
 */

/**
 * @param {string} template
 * @param {Record<string, string>} values
 */
function fill(template, values) {
    return template.replace(/%\((\w+)\)s/g, (match, name) => values[name] ?? match);
}

/** @param {HTMLElement} root */
function readStrings(root) {
    try {
        return { ...DEFAULT_STRINGS, ...JSON.parse(root.dataset.i18n || '{}') };
    } catch {
        return DEFAULT_STRINGS;
    }
}

/**
 * Group days into periods of `size` days, counting back from the last day so the latest period ends today.
 * @param {(number | null)[]} daily
 * @param {number} size
 * @param {(number | null)[]} [rolling] a rolling series to sample at each period's end, for counts that don't add up
 * @returns {Bucket[]}
 */
export function bucketize(daily, size, rolling) {
    const buckets = [];
    for (let end = daily.length - 1; end >= 0; end -= size) {
        const start = Math.max(0, end - size + 1);
        let value;
        if (size === 1) value = daily[end];
        else if (rolling) value = rolling[end];
        else {
            const days = daily.slice(start, end + 1).filter(v => v !== null);
            value = days.length ? days.reduce((a, b) => a + b, 0) : null;
        }
        buckets.unshift({ start, end, value });
    }
    return buckets;
}

/**
 * The last `count` buckets, and the `count` before them lined up beside them, padded with nulls where history runs out.
 * @param {Bucket[]} buckets
 * @param {number} count
 */
export function splitPeriods(buckets, count) {
    const current = buckets.slice(-count);
    const before = buckets.slice(Math.max(0, buckets.length - 2 * count), Math.max(0, buckets.length - count));
    const previous = [...Array(current.length - before.length).fill(null), ...before];
    return { current, previous };
}

/**
 * Point sizes for a line: a dot on the latest value and on any value with no neighbours, which would otherwise draw nothing.
 * @param {(number | null)[]} values
 */
export function pointRadii(values) {
    const last = values.findLastIndex(v => v !== null);
    return values.map((v, i) => (v !== null && (i === last || ((values[i - 1] ?? null) === null && (values[i + 1] ?? null) === null)) ? 3 : 0));
}

/**
 * @param {HTMLElement} root the page's `.tasks-stats` element
 */
export async function init(root) {
    const strings = readStrings(root);
    const style = getComputedStyle(root);
    const token = (/** @type {string} */ name) => style.getPropertyValue(name).trim();
    const bar = resolveColor(root, 'var(--color-stats-chart-bar)');
    const colors = {
        bar,
        // The day or period still being counted
        partial: withAlpha(bar, 0.45),
        area: withAlpha(bar, 0.25),
        previous: token('--color-text-secondary'),
        grid: token('--color-border-subtle'),
        text: token('--color-text'),
        surface: token('--color-surface')
    };
    Chart.defaults.font.family = token('--font-family-body');
    Chart.defaults.font.size = parseInt(token('--font-size-body-small'));
    Chart.defaults.color = colors.previous;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) Chart.defaults.animation = false;

    /** @type {TasksSeries} */
    let data;
    try {
        const response = await fetch(`/stats/tasks.json?days=${FETCH_DAYS}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        data = await response.json();
    } catch {
        const error = document.createElement('p');
        error.className = 'tasks-stats__error';
        error.textContent = strings.loadFailed;
        root.querySelector('.tasks-stats__cards')?.after(error);
        return;
    }

    const lang = document.documentElement.lang || undefined;
    const dayFormat = new Intl.DateTimeFormat(lang, { month: 'short', day: 'numeric', timeZone: 'UTC' });
    const fullFormat = new Intl.DateTimeFormat(lang, { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' });
    const numberFormat = new Intl.NumberFormat(lang);
    const percentFormat = new Intl.NumberFormat(lang, { style: 'percent', maximumFractionDigits: 1 });
    const dates = data.dates.map(d => new Date(`${d}T00:00:00Z`));
    const lastDay = dates.length - 1;
    const series = (/** @type {string} */ key) => data.series[key] || dates.map(() => null);

    const state = { days: 90, granularity: 'day', compare: true, metric: 'editors' };

    /** @param {Bucket} bucket */
    const shortLabel = bucket =>
        bucket.start === bucket.end ? dayFormat.format(dates[bucket.end]) : `${dayFormat.format(dates[bucket.start])} – ${dayFormat.format(dates[bucket.end])}`;
    /** @param {Bucket} bucket */
    const fullLabel = bucket =>
        bucket.start === bucket.end
            ? fullFormat.format(dates[bucket.end])
            : `${fullFormat.format(dates[bucket.start])} – ${fullFormat.format(dates[bucket.end])}`;
    /** @param {Bucket} bucket */
    const inProgressNote = bucket => (bucket.end !== lastDay ? '' : bucket.start === bucket.end ? strings.todaySoFar : strings.periodSoFar);
    const bucketCount = () => Math.max(1, Math.round(state.days / BUCKET_DAYS[state.granularity]));

    /**
     * @param {string} name
     * @param {import('chart.js').ChartConfiguration} config
     */
    function draw(name, config) {
        const canvas = /** @type {HTMLCanvasElement} */ (root.querySelector(`canvas[data-chart="${name}"]`));
        const existing = Chart.getChart(canvas);
        if (existing) {
            existing.data = config.data;
            existing.options = config.options || {};
            existing.update();
        } else {
            new Chart(canvas, config);
        }
        const hasData = config.data.datasets.some(dataset => dataset.data.some(v => v !== null));
        let empty = canvas.parentElement?.querySelector('.tasks-stats__empty');
        if (!hasData && !empty) {
            empty = document.createElement('p');
            empty.className = 'tasks-stats__note tasks-stats__empty';
            empty.textContent = strings.noData;
            canvas.parentElement?.append(empty);
        }
        if (hasData) empty?.remove();
    }

    /**
     * @param {object} [overrides]
     * @param {Partial<import('chart.js').TooltipCallbacks<any>>} [overrides.tooltip]
     * @param {object} [overrides.y]
     */
    function options({ tooltip = {}, y = {} } = {}) {
        return {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: /** @type {const} */ ('index'), intersect: false },
            scales: {
                x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8 } },
                y: { beginAtZero: true, border: { display: false }, grid: { color: colors.grid }, ticks: { precision: 0 }, ...y }
            },
            plugins: {
                tooltip: {
                    backgroundColor: colors.surface,
                    titleColor: colors.text,
                    bodyColor: colors.text,
                    footerColor: colors.previous,
                    borderColor: colors.grid,
                    borderWidth: 1,
                    padding: 10,
                    displayColors: false,
                    callbacks: tooltip
                }
            }
        };
    }

    /** @param {Bucket[]} buckets */
    function barDataset(buckets) {
        return {
            type: /** @type {const} */ ('bar'),
            data: buckets.map(b => b.value),
            backgroundColor: buckets.map(b => (b.end === lastDay ? colors.partial : colors.bar)),
            borderRadius: 2,
            barPercentage: buckets.length > 120 ? 1 : 0.8,
            categoryPercentage: 0.9,
            order: 2
        };
    }

    function drawMain() {
        const metric = METRICS[state.metric];
        const size = BUCKET_DAYS[state.granularity];
        const rolling = metric.windows && state.granularity !== 'day' ? series(metric.windows[state.granularity]) : undefined;
        const { current, previous } = splitPeriods(bucketize(series(metric.daily), size, rolling), bucketCount());
        const datasets = [barDataset(current)];
        if (state.compare) {
            datasets.push({
                type: 'line',
                data: previous.map(b => b?.value ?? null),
                borderColor: colors.previous,
                borderDash: [4, 4],
                borderWidth: 1.5,
                pointRadius: 0,
                pointHitRadius: 0,
                tension: 0.25,
                order: 1
            });
        }
        draw('main', {
            type: 'bar',
            data: { labels: current.map(shortLabel), datasets },
            options: options({
                tooltip: {
                    title: items => fullLabel(current[items[0].dataIndex]),
                    label: item => {
                        if (item.dataset.type === 'line') return fill(strings.previousValue, { count: numberFormat.format(item.raw) });
                        const before = previous[item.dataIndex]?.value;
                        if (!before) return numberFormat.format(item.raw);
                        const change = (item.raw - before) / before;
                        return `${numberFormat.format(item.raw)}  (${fill(strings.change, { change: `${change >= 0 ? '+' : ''}${percentFormat.format(change)}` })})`;
                    },
                    footer: items => inProgressNote(current[items[0].dataIndex])
                }
            })
        });
    }

    // The initiative and guardrail lines are daily snapshots, so they follow the range but not the grouping.
    function drawDailyLines() {
        const days = bucketize(series('initiative_open_gaps'), 1).slice(-state.days);
        draw('initiative', {
            type: 'line',
            data: {
                labels: days.map(shortLabel),
                datasets: [
                    {
                        data: days.map(b => b.value),
                        borderColor: colors.bar,
                        backgroundColor: colors.area,
                        pointBackgroundColor: colors.bar,
                        fill: true,
                        borderWidth: 2.5,
                        pointRadius: pointRadii(days.map(b => b.value)),
                        tension: 0.2
                    }
                ]
            },
            options: options({
                y: { beginAtZero: false },
                tooltip: {
                    title: items => fullLabel(days[items[0].dataIndex]),
                    label: item => fill(strings.openDetails, { count: numberFormat.format(item.raw) })
                }
            })
        });

        const undone = series('tasks_saves_undone_28d');
        const saves = series('tasks_saves_28d');
        const shares = bucketize(undone, 1)
            .slice(-state.days)
            .map(b => ({ ...b, value: b.value !== null && saves[b.end] ? (b.value / /** @type {number} */ (saves[b.end])) * 100 : null }));
        draw('undone', {
            type: 'line',
            data: {
                labels: shares.map(shortLabel),
                datasets: [
                    {
                        data: shares.map(b => b.value),
                        borderColor: colors.bar,
                        pointBackgroundColor: colors.bar,
                        borderWidth: 2.5,
                        pointRadius: pointRadii(shares.map(b => b.value)),
                        tension: 0.25
                    }
                ]
            },
            options: options({
                y: { suggestedMax: 25, ticks: { callback: (/** @type {number} */ v) => percentFormat.format(v / 100) } },
                tooltip: {
                    title: items => fullLabel(shares[items[0].dataIndex]),
                    label: item => {
                        const day = shares[item.dataIndex].end;
                        return fill(strings.undoneShare, {
                            share: percentFormat.format(item.raw / 100),
                            undone: numberFormat.format(/** @type {number} */ (undone[day])),
                            saves: numberFormat.format(/** @type {number} */ (saves[day]))
                        });
                    }
                }
            })
        });
    }

    const title = /** @type {HTMLElement} */ (root.querySelector('.tasks-stats__chart-title'));
    const unit = /** @type {HTMLElement} */ (root.querySelector('.tasks-stats__chart-unit'));
    const legend = /** @type {HTMLElement} */ (root.querySelector('.tasks-stats__legend'));
    const note = /** @type {HTMLElement} */ (root.querySelector('.tasks-stats__chart-note'));
    const cards = /** @type {NodeListOf<HTMLButtonElement>} */ (root.querySelectorAll('.tasks-stats__card'));
    const units = { day: strings.perDay, week: strings.perWeek, month: strings.perMonth };

    function update() {
        unit.textContent = units[state.granularity];
        legend.hidden = !state.compare;
        drawMain();
    }

    cards.forEach(card =>
        card.addEventListener('click', () => {
            state.metric = card.dataset.metric || 'editors';
            cards.forEach(other => other.setAttribute('aria-pressed', String(other === card)));
            title.textContent = card.querySelector('.tasks-stats__card-label')?.textContent || '';
            note.textContent = card.dataset.note || '';
            drawMain();
        })
    );
    root.querySelector('.tasks-stats__range')?.addEventListener('ol-segmented-control-change', event => {
        state.days = Number(/** @type {CustomEvent} */ (event).detail.value);
        update();
        drawDailyLines();
    });
    root.querySelector('.tasks-stats__granularity')?.addEventListener('ol-segmented-control-change', event => {
        state.granularity = /** @type {CustomEvent} */ (event).detail.value;
        update();
    });
    root.querySelector('.tasks-stats__compare')?.addEventListener('ol-toggle-change', event => {
        state.compare = /** @type {CustomEvent} */ (event).detail.checked;
        update();
    });

    update();
    drawDailyLines();
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
