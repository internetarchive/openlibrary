// @ts-check
import { BarController, BarElement, CategoryScale, Chart, Filler, LinearScale, LineController, LineElement, PointElement, Tooltip } from 'chart.js';

Chart.register(BarController, BarElement, CategoryScale, Filler, LinearScale, LineController, LineElement, PointElement, Tooltip);

/** English fallbacks; the page's `data-i18n` overrides them. Keys match build_tasks_stats_i18n in openlibrary/views/loanstats.py. */
export const DEFAULT_STRINGS = {
    perDay: 'Per day',
    perWeek: 'Per week',
    perMonth: 'Per 4 weeks',
    earlier7: 'A week earlier',
    earlier28: '4 weeks earlier',
    earlierValue7: 'A week earlier: %(count)s',
    earlierValue28: '4 weeks earlier: %(count)s',
    earlierChange7: '%(change)s vs a week earlier',
    earlierChange28: '%(change)s vs 4 weeks earlier',
    cardChange7: '%(change)s vs previous 7 days',
    cardChange28: '%(change)s vs previous 28 days',
    split: '%(returning)s returning · %(first_time)s first-time',
    perEditor: '≈ %(count)s per editor',
    tasksShareDetail: 'of edits · %(share)s of editors',
    shareOfEdits: '%(share)s of all edits',
    shareOfEditors: '%(share)s of all editors',
    perEditorOverall: 'vs ≈ %(count)s edits per editor overall',
    todaySoFar: 'Today so far, updated hourly',
    periodSoFar: 'Still in progress',
    openDetails: '%(count)s details still open',
    tasksUndone: 'Tasks: %(share)s undone, %(undone)s of %(total)s saves',
    otherUndone: 'Outside Tasks: %(share)s undone, %(undone)s of %(total)s fills',
    noData: 'No counts for this range yet.',
    returning: 'Returning',
    firstTime: 'First edit ever',
    otherEdits: 'Records and other pages',
    lists: 'Lists',
    tasks: 'Tasks',
    total: 'Total: %(count)s',
    ofEdits: 'Of edits',
    ofEditors: 'Of editors',
    perDayAverage: 'Per day, averaged',
    loadFailed: "The charts couldn't load. Reload the page to try again."
};

// Enough for a 12-month range; matches MAX_DAYS in openlibrary/fastapi/stats.py.
const FETCH_DAYS = 400;
const BUCKET_DAYS = { day: 1, week: 7, month: 28 };

/**
 * @typedef {object} TasksSeries
 * @property {string[]} dates ISO dates, oldest first, ending today
 * @property {Record<string, (number | null)[]>} series
 * @property {Record<string, (number | null)[]>} initiatives details still open on each initiative's list, by slug
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
 * Group days into periods of `size` days, counting back from the last day so the latest period ends today. Days left
 * over at the start are dropped, since a short period can't be compared with a full one.
 * @param {(number | null)[]} daily
 * @param {number} size
 * @param {(number | null)[]} [rolling] a rolling series to sample at each period's end, for counts that don't add up
 * @param {boolean} [average] the period's daily average instead of its sum
 * @returns {Bucket[]}
 */
export function bucketize(daily, size, rolling, average = false) {
    const buckets = [];
    for (let end = daily.length - 1; end - size + 1 >= 0; end -= size) {
        const start = end - size + 1;
        let value;
        if (size === 1) value = daily[end];
        else if (rolling) value = rolling[end];
        else {
            const days = daily.slice(start, end + 1).filter(v => v !== null);
            value = days.length ? days.reduce((a, b) => a + b, 0) / (average ? days.length : 1) : null;
        }
        buckets.unshift({ start, end, value });
    }
    return buckets;
}

/**
 * The last `count` buckets, each beside the bucket `shift` before it, null where history runs out.
 * @param {Bucket[]} buckets
 * @param {number} count
 * @param {number} shift
 */
export function shiftPeriods(buckets, count, shift) {
    const current = buckets.slice(-count);
    const offset = buckets.length - current.length - shift;
    const previous = current.map((_, i) => buckets[offset + i] ?? null);
    return { current, previous };
}

/**
 * The change from `before` to `now` the way the server's cards show it: a direction and a one-decimal percentage, or null
 * without an earlier value. Matches format_change in openlibrary/views/loanstats.py.
 * @param {number | null} now
 * @param {number | null | undefined} before
 */
export function cardChange(now, before) {
    if (now === null || !before) return null;
    const change = ((now - before) / before) * 100;
    return { direction: change >= 0.5 ? 'up' : change <= -0.5 ? 'down' : 'flat', text: `${Math.abs(change).toFixed(1)}%` };
}

/**
 * One series less another, day by day: null where either is missing, never below zero.
 * @param {(number | null)[]} a
 * @param {...(number | null)[]} others
 */
export function subtract(a, ...others) {
    return a.map((v, i) =>
        v === null || others.some(o => o[i] === null)
            ? null
            : Math.max(
                  0,
                  others.reduce((rest, o) => rest - /** @type {number} */ (o[i]), v)
              )
    );
}

/**
 * `num` over `den`, period by period, times `scale`: null without both.
 * @param {Bucket[]} num
 * @param {Bucket[]} den
 * @param {number} scale
 * @returns {Bucket[]}
 */
export function ratio(num, den, scale) {
    return num.map((b, i) => ({ ...b, value: b.value !== null && den[i]?.value ? (b.value / /** @type {number} */ (den[i].value)) * scale : null }));
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
 * @typedef {object} Part
 * @property {string} label
 * @property {string} color
 * @property {Bucket[]} buckets
 */

/**
 * @typedef {object} Metric
 * @property {Part[]} parts stacked bottom up
 * @property {Bucket[]} total what the previous period and the change compare
 * @property {'count' | 'percent' | 'decimal'} format
 * @property {boolean} [average] week and month bars are daily averages
 * @property {(number | null)[][]} [complete] daily series a card needs every day of, or its sum would read as a drop
 */

/**
 * @param {HTMLElement} root the page's `.tasks-stats` element
 */
export async function init(root) {
    const strings = readStrings(root);
    const style = getComputedStyle(root);
    const token = (/** @type {string} */ name) => style.getPropertyValue(name).trim();
    const bar = resolveColor(root, 'var(--color-stats-chart-bar)');
    const accent = resolveColor(root, 'var(--color-stats-chart-accent)');
    const muted = resolveColor(root, 'var(--color-stats-chart-muted)');
    const colors = {
        bar,
        accent,
        muted,
        area: withAlpha(bar, 0.25),
        previous: resolveColor(root, 'var(--color-text-secondary)'),
        grid: token('--color-border-subtle'),
        text: resolveColor(root, 'var(--color-text)'),
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
        root.querySelector('.tasks-stats__main')?.before(error);
        return;
    }

    const lang = document.documentElement.lang || undefined;
    const dayFormat = new Intl.DateTimeFormat(lang, { month: 'short', day: 'numeric', timeZone: 'UTC' });
    const fullFormat = new Intl.DateTimeFormat(lang, { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' });
    const numberFormat = new Intl.NumberFormat(lang, { maximumFractionDigits: 0 });
    const decimalFormat = new Intl.NumberFormat(lang, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    const percentFormat = new Intl.NumberFormat(lang, { style: 'percent', maximumFractionDigits: 1 });
    const compactFormat = new Intl.NumberFormat(lang, { notation: 'compact' });
    const formats = {
        count: (/** @type {number} */ v) => numberFormat.format(v),
        decimal: (/** @type {number} */ v) => decimalFormat.format(v),
        percent: (/** @type {number} */ v) => percentFormat.format(v / 100)
    };
    const dates = data.dates.map(d => new Date(`${d}T00:00:00Z`));
    const lastDay = dates.length - 1;
    const fullSeries = (/** @type {string} */ key) => data.series[key] || dates.map(() => null);
    const series = fullSeries;

    /**
     * Every chart and card metric, over the days up to `n`. The cards end on the last day the stats script has gathered,
     * like the server's, so a late run reads as the latest counts rather than a dash.
     * @param {number} n
     */
    function buildMetrics(n) {
        const series = (/** @type {string} */ key) => fullSeries(key).slice(0, n);
        // Edits split by where they were saved. A day with edits but no list or Tasks count had none of those.
        const edits = series('catalog_edits');
        const orZero = (/** @type {(number | null)[]} */ values) => values.map((v, i) => (edits[i] === null ? null : (v ?? 0)));
        const lists = orZero(series('list_edits'));
        const tasksSaves = orZero(series('tasks_saves_1d'));
        // Today's Graphite count is partial, so it's left out like the server's cards leave it out.
        const visitors = series('visitors').map((v, i) => (i === lastDay ? null : v));
        // Only days with both counts, so a missing visitor count doesn't read as a jump in the ratio.
        const pairedEdits = edits.map((v, i) => (visitors[i] === null ? null : v));

        /**
         * People can't be added up across days, so week and month views of them take the stored 7- or 28-day window ending on
         * the period's last day instead.
         * @param {string} prefix e.g. `catalog_editors`, with `_1d`, `_7d` and `_28d` keys
         * @param {number} size
         */
        const people = (prefix, size) => bucketize(series(`${prefix}_1d`), size, size === 1 ? undefined : series(`${prefix}_${size === 7 ? 7 : 28}d`));
        const sum = (/** @type {(number | null)[]} */ daily, /** @type {number} */ size) => bucketize(daily, size);
        /** @param {Part[]} parts */
        const stackTotal = parts =>
            parts[0].buckets.map((b, i) => {
                const values = parts.map(p => p.buckets[i].value);
                return { ...b, value: values.every(v => v === null) ? null : values.reduce((a, v) => /** @type {number} */ (a) + (v ?? 0), 0) };
            });

        /** @type {Record<string, (size: number) => Metric>} */
        const METRICS = {
            editors: size => {
                const all = people('catalog_editors', size);
                const firstTime = people('new_catalog_editors', size);
                const returning = all.map((b, i) => ({
                    ...b,
                    value: b.value === null || firstTime[i].value === null ? null : Math.max(0, b.value - firstTime[i].value)
                }));
                return {
                    parts: [
                        { label: strings.returning, color: colors.bar, buckets: returning },
                        { label: strings.firstTime, color: colors.accent, buckets: firstTime }
                    ],
                    total: all,
                    format: 'count'
                };
            },
            edits: size => {
                const parts = [
                    { label: strings.otherEdits, color: colors.bar, buckets: sum(subtract(edits, lists, tasksSaves), size) },
                    { label: strings.lists, color: colors.muted, buckets: sum(lists, size) },
                    { label: strings.tasks, color: colors.accent, buckets: sum(tasksSaves, size) }
                ];
                return { parts, total: stackTotal(parts), format: 'count', complete: [edits] };
            },
            visitors: size => single(bucketize(visitors, size, undefined, true), 'count', true),
            edits_per_visitors: size => single(ratio(sum(pairedEdits, size), sum(visitors, size), 1000), 'decimal'),
            tasks_share: size => ({ ...single(ratio(sum(tasksSaves, size), sum(edits, size), 100), 'percent'), complete: [edits] }),
            saves: size => single(sum(series('tasks_saves_1d'), size), 'count'),
            tasks_editors: size => single(people('tasks_editors', size), 'count'),
            saves_per_editor: size => single(ratio(sum(series('tasks_saves_1d'), size), people('tasks_editors', size), 1), 'decimal')
        };
        return { METRICS, edits, tasksSaves, visitors, pairedEdits };
    }
    const { METRICS, edits, tasksSaves, visitors, pairedEdits } = buildMetrics(dates.length);
    const gathered = Math.max(...['catalog_editors_1d', 'catalog_edits', 'tasks_saves_1d'].map(key => fullSeries(key).findLastIndex(v => v !== null)));
    const CARD_METRICS = gathered >= 0 ? buildMetrics(gathered + 1).METRICS : METRICS;

    /**
     * @param {Bucket[]} buckets
     * @param {Metric['format']} format
     * @param {boolean} [average]
     * @returns {Metric}
     */
    function single(buckets, format, average = false) {
        return { parts: [{ label: '', color: colors.bar, buckets }], total: buckets, format, average };
    }

    const projects = /** @type {NodeListOf<HTMLButtonElement>} */ (root.querySelectorAll('.tasks-stats__card[data-initiative]'));
    const pressed = [...projects].find(card => card.getAttribute('aria-pressed') === 'true');
    const state = {
        scope: root.dataset.scope || 'all',
        days: 90,
        granularity: 'day',
        compare: true,
        metric: '',
        // The cards' window, and how far back the chart's dashed line reaches
        window: 28,
        initiative: pressed?.dataset.initiative || ''
    };

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
    // Rounded down, so the chart never reaches back further than the chosen range.
    const bucketCount = () => Math.max(1, Math.floor(state.days / BUCKET_DAYS[state.granularity]));

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
     * @param {boolean} [overrides.stacked]
     * @param {number} [overrides.xTicks]
     */
    function options({ tooltip = {}, y = {}, stacked = false, xTicks = 8 } = {}) {
        return {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: /** @type {const} */ ('index'), intersect: false },
            scales: {
                x: { stacked, grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: xTicks } },
                y: { stacked, beginAtZero: true, border: { display: false }, grid: { color: colors.grid }, ticks: { precision: 0 }, ...y }
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

    /** @param {Metric['format']} format */
    const axis = format => (format === 'count' ? {} : { ticks: { callback: (/** @type {number} */ v) => formats[format](v) } });

    function drawMain() {
        const metric = METRICS[state.metric](BUCKET_DAYS[state.granularity]);
        const count = bucketCount();
        const format = formats[metric.format];
        // The dashed line is the chart shifted back by the window, or by one bar when bars are wider than it.
        const shift = Math.max(1, Math.round(state.window / BUCKET_DAYS[state.granularity]));
        const ago = shift * BUCKET_DAYS[state.granularity] <= 7 ? 7 : 28;
        const { current, previous } = shiftPeriods(metric.total, count, shift);
        legend.textContent = strings[`earlier${ago}`];
        const stacked = metric.parts.length > 1;
        const datasets = metric.parts.map(part => {
            const buckets = part.buckets.slice(-count);
            return {
                type: /** @type {const} */ ('bar'),
                label: part.label,
                data: buckets.map(b => b.value),
                // The day or period still being counted is paler
                backgroundColor: buckets.map(b => (b.end === lastDay ? withAlpha(part.color, 0.45) : part.color)),
                borderRadius: stacked ? 0 : 2,
                barPercentage: buckets.length > 120 ? 1 : 0.8,
                categoryPercentage: 0.9,
                stack: 'parts',
                order: 2
            };
        });
        if (state.compare) {
            datasets.push(
                /** @type {any} */ ({
                    type: 'line',
                    data: previous.map(b => b?.value ?? null),
                    borderColor: colors.previous,
                    borderDash: [4, 4],
                    borderWidth: 1.5,
                    pointRadius: 0,
                    pointHitRadius: 0,
                    tension: 0.25,
                    stack: 'previous',
                    order: 1
                })
            );
        }
        /** @param {number} index */
        const changeText = index => {
            const now = current[index].value;
            const before = previous[index]?.value;
            if (!state.compare || !before || now === null) return '';
            const change = (now - before) / before;
            return fill(strings[`earlierChange${ago}`], { change: `${change >= 0 ? '+' : ''}${percentFormat.format(change)}` });
        };
        draw('main', {
            type: 'bar',
            data: { labels: current.map(shortLabel), datasets },
            options: options({
                stacked,
                y: axis(metric.format),
                tooltip: {
                    title: items => fullLabel(current[items[0].dataIndex]),
                    label: item => {
                        if (item.dataset.type === 'line') return fill(strings[`earlierValue${ago}`], { count: format(item.raw) });
                        if (stacked) return `${item.dataset.label}: ${format(item.raw)}`;
                        const change = changeText(item.dataIndex);
                        return change ? `${format(item.raw)}  (${change})` : format(item.raw);
                    },
                    footer: items => {
                        const index = items[0].dataIndex;
                        const total = current[index].value;
                        const lines = [];
                        if (stacked && total !== null) {
                            const change = changeText(index);
                            lines.push(fill(strings.total, { count: format(total) }) + (change ? `  (${change})` : ''));
                        }
                        lines.push(inProgressNote(current[index]));
                        return lines.filter(Boolean);
                    }
                }
            })
        });
        unit.textContent = metric.average && state.granularity !== 'day' ? strings.perDayAverage : units[state.granularity];
        parts.replaceChildren(
            ...(stacked ? metric.parts : []).map(part => {
                const item = document.createElement('span');
                item.className = 'tasks-stats__part';
                item.style.setProperty('--swatch', part.color);
                item.textContent = part.label;
                return item;
            })
        );
    }

    /**
     * A daily line over the chosen range.
     * @param {string} name
     * @param {{values: (number | null)[], color: string, dashed?: boolean, label?: string}[]} lines
     * @param {Metric['format']} format
     * @param {object} [extra]
     * @param {boolean} [extra.small]
     * @param {boolean} [extra.area]
     */
    function drawLines(name, lines, format, { small = false, area = false } = {}) {
        const days = bucketize(lines[0].values, 1).slice(-state.days);
        draw(name, {
            type: 'line',
            data: {
                labels: days.map(shortLabel),
                datasets: lines.map(line => {
                    // Today is still being counted, so a line would end in a false drop.
                    const values = days.map(d => (d.end === lastDay ? null : line.values[d.end]));
                    return {
                        label: line.label,
                        data: values,
                        borderColor: line.color,
                        backgroundColor: withAlpha(line.color, 0.2),
                        pointBackgroundColor: line.color,
                        fill: area,
                        borderDash: line.dashed ? [4, 4] : [],
                        borderWidth: line.dashed ? 1.5 : 2,
                        pointRadius: pointRadii(values),
                        tension: 0.25
                    };
                })
            },
            options: options({
                xTicks: small ? 4 : 8,
                // Small multiples share one axis width, so their days line up down the column.
                y: small
                    ? {
                          ticks: {
                              maxTicksLimit: 3,
                              callback: (/** @type {number} */ v) => (format === 'count' ? compactFormat.format(v) : formats[format](v))
                          },
                          afterFit: (/** @type {{width: number}} */ scale) => {
                              scale.width = 44;
                          }
                      }
                    : axis(format),
                tooltip: {
                    title: items => fullLabel(days[items[0].dataIndex]),
                    label: item => (item.dataset.label ? `${item.dataset.label}: ` : '') + formats[format](item.raw)
                }
            })
        });
    }

    // Daily lines follow the range but not the grouping.
    function drawAllPanels() {
        const perDay = (/** @type {(number | null)[]} */ num, /** @type {(number | null)[]} */ den, /** @type {number} */ scale) =>
            num.map((v, i) => (v !== null && den[i] ? (v / /** @type {number} */ (den[i])) * scale : null));
        drawLines(
            'share',
            [
                { values: perDay(tasksSaves, edits, 100), color: colors.accent, label: strings.ofEdits },
                {
                    values: perDay(series('tasks_editors_1d'), series('catalog_editors_1d'), 100),
                    color: colors.previous,
                    dashed: true,
                    label: strings.ofEditors
                }
            ],
            'percent'
        );
        drawLines('visitors', [{ values: visitors, color: colors.accent }], 'count', { small: true, area: true });
        drawLines('edits', [{ values: edits, color: colors.bar }], 'count', { small: true, area: true });
        drawLines('ratio', [{ values: perDay(pairedEdits, visitors, 1000), color: colors.text }], 'decimal', { small: true });
    }

    function drawTasksPanels() {
        const openGaps = data.initiatives?.[state.initiative] || dates.map(() => null);
        const days = bucketize(openGaps, 1).slice(-state.days);
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

        // Each line is a share of the 28 days to that day, left out where fewer than `minSample` saves stand behind it.
        const minSample = Number(root.dataset.minSample) || 0;
        const rates = [
            { undone: series('tasks_saves_undone_28d'), total: series('tasks_saves_28d'), label: strings.tasksUndone },
            { undone: series('other_fills_undone_28d'), total: series('other_fills_28d'), label: strings.otherUndone }
        ];
        const undoneDays = bucketize(rates[0].undone, 1).slice(-state.days);
        const shares = rates.map(({ undone, total }) =>
            undoneDays.map(({ end }) => {
                const count = undone[end];
                const of = total[end];
                return count !== null && of !== null && of >= minSample && of > 0 ? (count / of) * 100 : null;
            })
        );
        draw('undone', {
            type: 'line',
            data: {
                labels: undoneDays.map(shortLabel),
                datasets: [
                    {
                        data: shares[0],
                        borderColor: colors.bar,
                        pointBackgroundColor: colors.bar,
                        borderWidth: 2.5,
                        pointRadius: pointRadii(shares[0]),
                        tension: 0.25
                    },
                    {
                        data: shares[1],
                        borderColor: colors.previous,
                        pointBackgroundColor: colors.previous,
                        borderDash: [4, 4],
                        borderWidth: 1.5,
                        pointRadius: pointRadii(shares[1]),
                        tension: 0.25
                    }
                ]
            },
            options: options({
                y: { suggestedMax: 25, ticks: { callback: (/** @type {number} */ v) => percentFormat.format(v / 100) } },
                tooltip: {
                    title: items => fullLabel(undoneDays[items[0].dataIndex]),
                    label: item => {
                        const { undone, total, label } = rates[item.datasetIndex];
                        const day = undoneDays[item.dataIndex].end;
                        return fill(label, {
                            share: percentFormat.format(item.raw / 100),
                            undone: numberFormat.format(/** @type {number} */ (undone[day])),
                            total: numberFormat.format(/** @type {number} */ (total[day]))
                        });
                    }
                }
            })
        });
    }

    const drawPanels = () => (state.scope === 'tasks' ? drawTasksPanels() : drawAllPanels());

    const title = /** @type {HTMLElement} */ (root.querySelector('.tasks-stats__chart-title'));
    const unit = /** @type {HTMLElement} */ (root.querySelector('.tasks-stats__chart-unit'));
    const legend = /** @type {HTMLElement} */ (root.querySelector('.tasks-stats__legend-previous'));
    const parts = /** @type {HTMLElement} */ (root.querySelector('.tasks-stats__parts'));
    const note = /** @type {HTMLElement} */ (root.querySelector('.tasks-stats__chart-note'));
    const cards = /** @type {NodeListOf<HTMLButtonElement>} */ (root.querySelectorAll('.tasks-stats__card[data-metric]'));
    const units = { day: strings.perDay, week: strings.perWeek, month: strings.perMonth };

    /** @param {HTMLButtonElement} card */
    function choose(card) {
        state.metric = card.dataset.metric || 'editors';
        card.closest('[data-scope]')
            ?.querySelectorAll('.tasks-stats__card[data-metric]')
            .forEach(other => other.setAttribute('aria-pressed', String(other === card)));
        title.textContent = card.querySelector('.tasks-stats__card-label')?.textContent || '';
        note.textContent = card.dataset.note || '';
        drawMain();
    }

    /** @param {string} scope */
    function showScope(scope) {
        state.scope = scope;
        root.dataset.scope = scope;
        root.querySelectorAll('[data-scope]').forEach(el => {
            /** @type {HTMLElement} */ (el).hidden = /** @type {HTMLElement} */ (el).dataset.scope !== scope;
        });
        const group = root.querySelector(`.tasks-stats__cards[data-scope="${scope}"]`);
        const card = group?.querySelector('[aria-pressed="true"]') || group?.querySelector('.tasks-stats__card');
        if (card) choose(/** @type {HTMLButtonElement} */ (card));
        drawPanels();
    }

    cards.forEach(card => card.addEventListener('click', () => choose(card)));
    root.querySelector('.tasks-stats__scope')?.addEventListener('ol-segmented-control-change', event => {
        const scope = /** @type {CustomEvent} */ (event).detail.value;
        const url = new URL(window.location.href);
        url.searchParams.set('scope', scope);
        history.replaceState(null, '', url);
        showScope(scope);
    });
    projects.forEach(card =>
        card.addEventListener('click', () => {
            state.initiative = card.dataset.initiative || '';
            projects.forEach(other => other.setAttribute('aria-pressed', String(other === card)));
            root.querySelectorAll('[data-initiative-figures]').forEach(figures => {
                /** @type {HTMLElement} */ (figures).hidden = /** @type {HTMLElement} */ (figures).dataset.initiativeFigures !== state.initiative;
            });
            drawTasksPanels();
        })
    );
    root.querySelector('.tasks-stats__range')?.addEventListener('ol-segmented-control-change', event => {
        state.days = Number(/** @type {CustomEvent} */ (event).detail.value);
        drawMain();
        drawPanels();
    });
    root.querySelector('.tasks-stats__granularity')?.addEventListener('ol-segmented-control-change', event => {
        state.granularity = /** @type {CustomEvent} */ (event).detail.value;
        drawMain();
    });
    root.querySelector('.tasks-stats__compare')?.addEventListener('ol-toggle-change', event => {
        state.compare = /** @type {CustomEvent} */ (event).detail.checked;
        legend.hidden = !state.compare;
        root.classList.toggle('tasks-stats--no-compare', !state.compare);
        drawMain();
    });

    root.querySelector('.tasks-stats__window')?.addEventListener('ol-segmented-control-change', event => {
        state.window = Number(/** @type {CustomEvent} */ (event).detail.value);
        updateCards();
        drawMain();
    });

    /**
     * A card's value over the window ending today, and over the window before it.
     * @param {string} name
     */
    function cardValues(name) {
        const metric = CARD_METRICS[name](state.window);
        /** @param {Bucket | undefined} bucket */
        const covered = bucket => bucket && (metric.complete || []).every(daily => daily.slice(bucket.start, bucket.end + 1).every(v => v !== null));
        const now = metric.total.at(-1);
        const before = metric.total.at(-2);
        return { metric, value: covered(now) ? (now?.value ?? null) : null, earlier: covered(before) ? (before?.value ?? null) : null };
    }

    // Card figures match the server's: whole numbers, and percentages to one decimal.
    const cardPercent = new Intl.NumberFormat(lang, { style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1 });
    const cardFormats = { ...formats, percent: (/** @type {number} */ v) => cardPercent.format(v / 100) };

    // Refill every card for the chosen window. The server renders the 28-day figures, so this runs only when the window changes.
    function updateCards() {
        /** @type {Record<string, number | null>} */
        const value = {};
        for (const name of Object.keys(METRICS)) value[name] = cardValues(name).value;
        const share = (/** @type {number | null} */ part, /** @type {number | null} */ whole) =>
            part !== null && whole ? cardPercent.format(part / whole) : null;
        const perEditor = value.edits !== null && value.editors ? numberFormat.format(value.edits / value.editors) : null;
        /** @type {Record<string, string | null | undefined>} */
        const details = {
            edits: perEditor && fill(strings.perEditor, { count: perEditor }),
            edits_per_visitors: '',
            tasks_share: value.tasks_share !== null ? (s => s && fill(strings.tasksShareDetail, { share: s }))(share(value.tasks_editors, value.editors)) : '',
            saves: (s => s && fill(strings.shareOfEdits, { share: s }))(share(value.saves, value.edits)),
            tasks_editors: (s => s && fill(strings.shareOfEditors, { share: s }))(share(value.tasks_editors, value.editors)),
            saves_per_editor: perEditor && fill(strings.perEditorOverall, { count: perEditor })
        };
        cards.forEach(card => {
            const name = card.dataset.metric || '';
            const { metric, value: now, earlier } = cardValues(name);
            const field = (/** @type {string} */ part) => /** @type {HTMLElement | null} */ (card.querySelector(`.tasks-stats__card-${part}`));
            const valueEl = field('value');
            if (valueEl) valueEl.textContent = now === null ? '—' : cardFormats[metric.format](now);
            const change = cardChange(now, earlier);
            const changeEl = field('change');
            if (changeEl) {
                changeEl.hidden = !change;
                changeEl.className = `tasks-stats__card-change${change ? ` tasks-stats__card-change--${change.direction}` : ''}`;
                const arrow = change?.direction === 'up' ? '▲ ' : change?.direction === 'down' ? '▼ ' : '';
                changeEl.textContent = change ? fill(strings[`cardChange${state.window}`], { change: arrow + change.text }) : '';
            }
            const detailEl = field('detail');
            if (name === 'editors') {
                const [returning, firstTime] = metric.parts.map(part => part.buckets.at(-1)?.value ?? null);
                const split = /** @type {HTMLElement | null} */ (card.querySelector('.tasks-stats__split-first'));
                if (split && now) split.style.width = `${((firstTime ?? 0) / now) * 100}%`;
                if (detailEl) {
                    detailEl.textContent =
                        returning !== null && firstTime !== null
                            ? fill(strings.split, { returning: numberFormat.format(returning), first_time: numberFormat.format(firstTime) })
                            : '';
                }
            } else if (detailEl && details[name] !== undefined) {
                // Visitors keeps the server's note, which says why the figure might be missing.
                detailEl.textContent = details[name] || '';
            }
        });
    }

    showScope(state.scope);
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
