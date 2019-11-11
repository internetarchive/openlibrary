import { loadGraphIfExists, loadEditionsGraph } from './plot';
import options from './options.js';

export function plotAdminGraphs() {
    loadGraphIfExists('editgraph', {}, 'edit(s) on');
    loadGraphIfExists('membergraph', {}, 'new members(s) on');
    loadGraphIfExists('works_minigraph', {}, ' works on ');
    loadGraphIfExists('editions_minigraph', {}, ' editions on ');
    loadGraphIfExists('covers_minigraph', {}, ' covers on ');
    loadGraphIfExists('authors_minigraph', {}, ' authors on ');
    loadGraphIfExists('lists_minigraph', {}, ' lists on ');
    loadGraphIfExists('members_minigraph', {}, ' members on ');
    loadGraphIfExists('books-added-per-day', options.booksAdded);
}

export function initHomepageGraphs() {
    loadGraphIfExists('visitors-graph', {}, 'unique visitors on', '#e44028');
    loadGraphIfExists('members-graph', {}, 'new members on', '#748d36');
    loadGraphIfExists('edits-graph', {}, 'catalog edits on', '#00636a');
    loadGraphIfExists('lists-graph', {}, 'lists created on', '#ffa337');
    loadGraphIfExists('ebooks-graph', {}, 'ebooks borrowed on', '#35672e');
}

export function initPublishersGraph() {
    if (document.getElementById('chartPubHistory')) {
        loadEditionsGraph('chartPubHistory', {}, 'editions in');
    }
}

export function init() {
    plotAdminGraphs();
    initHomepageGraphs();
    initPublishersGraph();
}
