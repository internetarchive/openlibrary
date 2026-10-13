import { loadEditionsGraph } from './plot';

export function initPublishersGraph() {
    if (document.getElementById('chartPubHistory')) {
        loadEditionsGraph('chartPubHistory', {}, 'editions in');
    }
}

export function init() {
    initPublishersGraph();
}
