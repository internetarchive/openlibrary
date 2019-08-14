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
    loadGraphIfExists('visitors', {}, 'unique visitors on', '#e44028');
    loadGraphIfExists('members', {}, 'new members on', '#748d36');
    loadGraphIfExists('edits', {}, 'catalog edits on', '#00636a');
    loadGraphIfExists('lists', {}, 'lists created on', '#ffa337');
    loadGraphIfExists('ebooks', {}, 'ebooks borrowed on', '#35672e');
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
