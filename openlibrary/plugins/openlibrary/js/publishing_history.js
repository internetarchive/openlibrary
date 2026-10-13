import { BarController, BarElement, CategoryScale, Chart, LinearScale, Tooltip } from 'chart.js';
import zoomPlugin from 'chartjs-plugin-zoom';

Chart.register(BarController, BarElement, CategoryScale, LinearScale, Tooltip, zoomPlugin);

/**
 * Draws the editions-per-year chart on subject and publisher pages. Clicking a year, or dragging
 * (pinching on touch screens) across a range to zoom in, filters the page's carousels to those years.
 */
export function init() {
    const container = document.getElementById('chartPubHistory');
    if (!container) return;
    /** @type {Map<number, number>} editions per year */
    const counts = new Map(JSON.parse(document.getElementById('graph-json-chartPubHistory').textContent));
    if (!counts.size) return;

    // Every year in the range, so years with no editions still get a slot on the axis
    const first = Math.min(...counts.keys());
    const last = Math.max(...counts.keys());
    const years = Array.from({ length: last - first + 1 }, (_, i) => first + i);

    /**
     * Filter the carousels (see Carousel.js) and show the reset link while zoomed in
     * @param {number} from
     * @param {number} to
     */
    function filter(from, to) {
        document.dispatchEvent(new CustomEvent('filter', { detail: { yearFrom: from, yearTo: to } }));
        const zoomed = from !== first || to !== last;
        document.querySelectorAll('.chartZoom').forEach(el => el.classList.toggle('hidden', !zoomed));
        document.querySelectorAll('.chartUnzoom').forEach(el => el.classList.toggle('hidden', zoomed));
    }

    const canvas = document.createElement('canvas');
    container.append(canvas);
    const chart = new Chart(canvas, {
        type: 'bar',
        data: {
            labels: years,
            datasets: [{ data: years.map(year => counts.get(year) ?? 0), backgroundColor: getComputedStyle(container).getPropertyValue('--color-chart-bar') }]
        },
        options: {
            maintainAspectRatio: false,
            // Without touchstart/touchmove, so a tap doesn't leave a hover tooltip behind; taps still arrive as clicks
            events: ['mousemove', 'mouseout', 'click'],
            // A click or tap anywhere in a year's column picks that year, not just on its (often thin) bar
            interaction: { axis: 'x', intersect: false },
            onClick: (e, [bar]) => bar && filter(years[bar.index], years[bar.index]),
            plugins: {
                zoom: {
                    zoom: {
                        drag: { enabled: true },
                        pinch: { enabled: true },
                        mode: 'x',
                        onZoomComplete: ({ chart }) => filter(years[chart.scales.x.min], years[chart.scales.x.max])
                    }
                }
            }
        }
    });

    // resetZoom() calls onZoomComplete, which clears the filter
    document.querySelectorAll('.resetSelection').forEach(link => link.addEventListener('click', () => chart.resetZoom()));

    const summary = document.querySelector('.clickdata');
    if (summary) summary.textContent = first === last ? `Published in ${first}` : `Published between ${first} & ${last}.`;
}
