import { BarController, BarElement, CategoryScale, Chart, LinearScale, Tooltip } from 'chart.js';

Chart.register(BarController, BarElement, CategoryScale, LinearScale, Tooltip);

/**
 * Draws the "New Books Imported Per Day" bar chart on /admin/imports.
 * @param {HTMLElement} container
 */
export function init(container) {
    /** @type {[number, number][]} [timestamp in ms, count] per day */
    const days = JSON.parse(document.getElementById('books-added-per-day-data').textContent);
    const canvas = document.createElement('canvas');
    container.append(canvas);
    new Chart(canvas, {
        type: 'bar',
        data: {
            labels: days.map(([ms]) => new Date(ms).toLocaleDateString(undefined, { timeZone: 'UTC', year: 'numeric', month: 'short', day: 'numeric' })),
            datasets: [{ data: days.map(([, count]) => count), backgroundColor: getComputedStyle(container).getPropertyValue('--color-stats-chart-bar') }]
        },
        options: { maintainAspectRatio: false, scales: { x: { ticks: { maxRotation: 0 } } } }
    });
}
