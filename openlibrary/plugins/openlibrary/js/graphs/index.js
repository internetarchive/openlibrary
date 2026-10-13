import { loadGraphIfExists, loadEditionsGraph } from './plot';
import options from './options.js';

export function plotAdminGraphs() {
    loadGraphIfExists('books-added-per-day', options.booksAdded);
}

export function initPublishersGraph() {
    if (document.getElementById('chartPubHistory')) {
        loadEditionsGraph('chartPubHistory', {}, 'editions in');
    }
}

export function init() {
    plotAdminGraphs();
    initPublishersGraph();
}
