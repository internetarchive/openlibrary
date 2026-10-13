// @ts-check
import { uniqBy } from './nonjquery_utils.js';
import { BarController, BarElement, CategoryScale, Chart, LinearScale } from 'chart.js';
import ChartDataLabels from 'chartjs-plugin-datalabels';

Chart.register(BarController, BarElement, CategoryScale, LinearScale);

const ROW_HEIGHT = 28;
// Room past the longest bar for its count
const COUNT_GUTTER = 32;

/**
 * Shorten a label with an ellipsis until it fits, so Chart.js doesn't clip it at the canvas edge
 * @param {CanvasRenderingContext2D} ctx
 * @param {string} label
 * @param {number} maxWidth
 */
function truncateToWidth(ctx, label, maxWidth) {
    ctx.save();
    ctx.font = `${Chart.defaults.font.size}px ${Chart.defaults.font.family}`;
    let text = label;
    while (text.length > 1 && ctx.measureText(text.length < label.length ? `${text}…` : text).width > maxWidth) {
        text = text.slice(0, -1);
    }
    ctx.restore();
    return text.length < label.length ? `${text.trimEnd()}…` : label;
}

/**
 * @typedef {object} Work
 * @property {string} key
 * @property {number | null} first_publish_year
 * @property {string | null} [first_publish_decade]
 * @property {string | null} [first_publish_century]
 */

/**
 * @typedef {object} Author
 * @property {string} key
 */

/**
 * @typedef {object} Config
 * @property {Work[]} works
 * @property {Author[]} authors
 * @property {string} lang
 * @property {string} charts_selector
 */

/**
 * @typedef {object} ChartConfig
 * @property {string} title
 * @property {'wd-chart' | 'work-chart'} type
 * @property {string} key
 * @property {string[]} [exclude]
 */

/**
 * @param {Config} config
 */
export function init(config) {
    const tokens = getComputedStyle(document.documentElement);
    const token = name => tokens.getPropertyValue(name).trim();
    const barColor = token('--color-chart-bar');
    const selectedBarColor = token('--color-chart-bar-selected');
    Chart.defaults.font.family = token('--font-family-body');
    Chart.defaults.font.size = parseInt(token('--font-size-body-small'));
    Chart.defaults.color = token('--color-text-secondary');
    /** @type {Chart[]} */
    const charts = [];
    const selectedWorksList = document.querySelector('.selected-works__list');

    /**
     * Highlight one bar (or none) across every chart, since the works list shows a single selection
     * @param {Chart} [selectedChart]
     * @param {number} [selectedIndex]
     */
    function selectBar(selectedChart, selectedIndex) {
        for (const chart of charts) {
            const dataset = chart.data.datasets[0];
            dataset.backgroundColor = dataset.data.map((_, i) => (chart === selectedChart && i === selectedIndex ? selectedBarColor : barColor));
            chart.update('none');
        }
    }
    const authors_by_id = Object.fromEntries(config.authors.map(a => [a.key, a]));

    /**
     *
     * @param {Config} config
     * @param {ChartConfig} chartConfig
     * @param {Element} container
     * @param {HTMLCanvasElement} canvas
     */
    function createWorkChart(config, chartConfig, container, canvas) {
        /** @type {{[key: string]: Work[]}} */
        const grouped = {};
        /** @type {Work[]} */
        const excluded = [];

        for (const work of config.works) {
            const result = getPath(work, chartConfig.key);
            const allKeys = Array.isArray(result) ? result : result ? [result] : [];
            const validKeys = [...new Set(allKeys.filter(key => key !== undefined && !chartConfig.exclude?.includes(key)))];
            if (!validKeys.length) {
                excluded.push(work);
                continue;
            }
            for (const key of validKeys) {
                grouped[key] = grouped[key] || [];
                grouped[key].push(work);
            }
        }

        const bars = Object.entries(grouped)
            .sort((a, b) => b[1].length - a[1].length)
            .slice(0, 20);
        // Let Chart.js size the canvas to the wrapper so its click hit-testing matches what is drawn
        /** @type {HTMLElement} */ (canvas.parentElement).style.height = `${bars.length * ROW_HEIGHT + 8}px`;
        canvas.setAttribute('role', 'img');
        canvas.setAttribute('aria-label', `${chartConfig.title}: ${bars.map(([label, works]) => `${label} (${works.length})`).join(', ')}`);
        const chart = new Chart(canvas, {
            type: 'bar',
            plugins: [ChartDataLabels],
            data: {
                labels: bars.map(b => b[0]),
                datasets: [
                    {
                        backgroundColor: barColor,
                        hoverBackgroundColor: selectedBarColor,
                        borderRadius: 4,
                        maxBarThickness: 20,
                        categoryPercentage: 0.7,
                        barPercentage: 1,
                        data: bars.map(b => b[1].length)
                    }
                ]
            },
            options: {
                indexAxis: 'y',
                maintainAspectRatio: false,
                layout: { padding: { right: COUNT_GUTTER } },
                scales: {
                    x: { display: false },
                    y: {
                        grid: { display: false },
                        border: { display: false },
                        ticks: {
                            // Chart.js caps the label column at half the width left after layout padding;
                            // leave room for the tick padding inside it
                            callback(value) {
                                return truncateToWidth(this.ctx, this.getLabelForValue(Number(value)), (this.chart.width - COUNT_GUTTER) / 2 - 12);
                            }
                        }
                    }
                },
                // Pick the nearest bar by height, so a tap anywhere across a row counts, not just on the bar
                interaction: { axis: 'y', intersect: false },
                onHover: (e, elements) => {
                    canvas.style.cursor = elements.length ? 'pointer' : 'default';
                },
                onClick: (e, [chartEl]) => {
                    if (chartEl) {
                        selectBar(chart, chartEl.index);
                        selectedWorksList.innerHTML = window.render_works_list(bars[chartEl.index][1]);
                    } else {
                        selectBar();
                        selectedWorksList.innerHTML = '';
                    }
                },
                plugins: {
                    tooltip: { enabled: false },
                    datalabels: {
                        color: token('--color-text'),
                        font: { weight: 600 },
                        anchor: 'end',
                        align: 'end',
                        offset: 4
                    }
                }
            }
        });
        charts.push(chart);

        container.insertAdjacentHTML('beforeend', window.render_excluded_works_list(excluded, config.works.length));
    }

    const defaultFieldRender = field => `OPTIONAL { ?x ${field.relation} ?${field.name}. }`;

    const SPARQL_FIELDS = [
        { name: 'sex', type: 'uri', relation: 'wdt:P21' },
        { name: 'dob', type: 'literal', relation: 'wdt:P569' },
        { name: 'country_of_citizenship', type: 'uri', relation: 'wdt:P27' },
        {
            name: 'country_of_birth',
            type: 'uri',
            relation: 'wdt:P19/wdt:P131*/wdt:P17',
            render: field => `
                OPTIONAL {
                    ?x ${field.relation} ?${field.name}.
                    OPTIONAL { ?country_of_birth wdt:P571 ?country_inception. }
                    OPTIONAL { ?country_of_birth wdt:P576 ?country_dissolution. }
                }
                # Limit to modern-day countries or the country that existed at the time
                # of the author's birth
                FILTER(!BOUND(?country_dissolution) || !BOUND(?dob) || (?dob >= ?country_inception && ?dob <= ?country_dissolution) ).
            `
        }
    ];

    function buildSparql(authors) {
        return `
            SELECT DISTINCT ?x ?xLabel ?olid
                ${SPARQL_FIELDS.map(f => `?${f.name} ${f.type === 'uri' ? `?${f.name}Label ` : ''}`).join('')}
            WHERE {
              VALUES ?olids { ${authors.map(a => `"${a.key.split('/')[2]}"`).join(' ')} }
              ?x wdt:P648 ?olids;
                 wdt:P648 ?olid.

              ${SPARQL_FIELDS.map(f => (f.render || defaultFieldRender)(f)).join('\n')}

              SERVICE wikibase:label { bd:serviceParam wikibase:language "[AUTO_LANGUAGE],${config.lang},en". }
            }
        `;
    }

    document.getElementById('wd-query-sample').href = `https://query.wikidata.org/#${encodeURIComponent(buildSparql(config.authors.slice(0, 20)))}`;

    const wdPromise = fetch('https://query.wikidata.org/sparql?format=json', {
        method: 'POST',
        body: new URLSearchParams({ query: buildSparql(config.authors) })
    })
        .then(r => r.json())
        .then(resp => {
            const bindings = resp.results.bindings;
            const grouped = {};
            for (const binding of bindings) {
                const qid = binding.x.value.split('/')[4];
                (grouped[qid] = grouped[qid] || []).push(binding);
            }
            const records = Object.entries(grouped).map(([qid, bindings]) => {
                const record = { qid, olids: [...new Set(bindings.map(x => x.olid.value))] };
                // { qid: Q123, olids: [ { value: }, {value: }], blah: [ {value:}, {value:} ], blahLabel: [{value:}, {value:},
                for (const { name, type } of SPARQL_FIELDS) {
                    if (type === 'uri') {
                        // need to dedupe whilst keeping labels in mind
                        const deduped = uniqBy(
                            bindings.filter(x => x[name]).map(x => ({ [name]: x[name], [`${name}Label`]: x[`${name}Label`] })),
                            x => x[name].value
                        );
                        record[name] = deduped.map(x => x[name]);
                        record[`${name}Label`] = deduped.map(x => x[`${name}Label`]);
                    } else {
                        record[name] = uniqBy(
                            bindings.map(x => x[name]),
                            x => x?.value
                        );
                    }
                }
                return record;
            });

            for (const record of records) {
                for (const olid of record.olids) {
                    if (`/authors/${olid}` in authors_by_id) {
                        authors_by_id[`/authors/${olid}`].wd = record;
                    }
                }
            }
        });

    // Add full authors to the works objects for easy reference
    for (const work of config.works) {
        work.authors = work.author_keys.map(key => authors_by_id[key]);
        work.first_publish_decade = work.first_publish_year ? `${Math.floor(work.first_publish_year / 10) * 10}s` : null;
        work.first_publish_century = work.first_publish_year ? `${Math.floor(work.first_publish_year / 100) * 100}s` : null;
    }

    for (const container of document.querySelectorAll(config.charts_selector)) {
        const chartConfig = JSON.parse(container.dataset['config']);
        const wrapper = document.createElement('div');
        wrapper.style.position = 'relative';
        const canvas = document.createElement('canvas');
        wrapper.append(canvas);
        container.append(wrapper);

        // Wait for the web font so canvas text isn't drawn in the fallback face
        if (chartConfig.type === 'work-chart') {
            document.fonts.ready.then(() => createWorkChart(config, chartConfig, container, canvas));
        } else if (chartConfig.type === 'wd-chart') {
            Promise.all([wdPromise, document.fonts.ready]).then(() => createWorkChart(config, chartConfig, container, canvas));
        }
    }
}

/**
 * @param {object} obj
 * @param {string} key
 * @return {any}
 */
function getPath(obj, key) {
    /**
     * @param {object} obj
     * @param {string[]} param1
     * @return {any}
     */
    function main(obj, [head, ...rest]) {
        if (typeof obj === 'undefined') return undefined;
        if (!head) return obj;
        if (head.endsWith('[]')) return obj[head.slice(0, -2)].flatMap(x => main(x, rest));
        else return main(obj[head], rest);
    }
    return main(obj, key.split('.'));
}
