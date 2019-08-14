import { loadGraph, loadEditionsGraph } from './plot';
import options from './options.js';

export function plotAdminGraphs() {
    if ($('#editgraph').length) {
        loadGraph('editgraph', {}, 'edit(s) on');
        loadGraph('membergraph', {}, 'new members(s) on');
    }
    if ($('#works_minigraph').length) {
        loadGraph('works_minigraph', {}, ' works on ');
        loadGraph('editions_minigraph', {}, ' editions on ');
        loadGraph('covers_minigraph', {}, ' covers on ');
        loadGraph('authors_minigraph', {}, ' authors on ');
        loadGraph('lists_minigraph', {}, ' lists on ');
        loadGraph('members_minigraph', {}, ' members on ');
    }
    if($('#books-added-per-day').length) {
        loadGraph('books-added-per-day', options.booksAdded);
    }
}

export function initHomepageGraphs() {
    if ( !document.getElementById('visitors') ) {
        return;
    }
    loadGraph('visitors', {}, 'unique visitors on', '#e44028');
    loadGraph('members', {}, 'new members on', '#748d36');
    loadGraph('edits', {}, 'catalog edits on', '#00636a');
    loadGraph('lists', {}, 'lists created on', '#ffa337');
    loadGraph('ebooks', {}, 'ebooks borrowed on', '#35672e');
}

export function initPublishersGraph() {
    if ( document.getElementById('chartPubHistory') ) {
        loadEditionsGraph('chartPubHistory', {}, 'editions in');
    }
}
