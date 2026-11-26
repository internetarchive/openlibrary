import $ from 'jquery';
import 'datatables.net-dt';
import '../../../../../static/css/legacy-datatables.css';
import { _, fmt } from '../i18n.js';

const DEFAULT_LENGTH = 3;
const LS_RESULTS_LENGTH_KEY = 'editions-table.resultsLength';
// DataTables' default layout ('lfrtip') minus 'p' — <ol-pagination> is the pager.
const DATATABLES_DOM = 'lfrti';

/** DataTables' own text; its `_MENU_`-style tokens fill the named placeholders. */
function datatablesLanguage() {
    return {
        // NOTE: %(menu)s is a dropdown of how many editions to show per page.
        lengthMenu: fmt(_('Show %(menu)s entries'), { menu: '_MENU_' }),
        search: _('Search:'),
        info: fmt(_('Showing %(start)s to %(end)s of %(total)s entries'), { start: '_START_', end: '_END_', total: '_TOTAL_' }),
        infoEmpty: _('Showing 0 to 0 of 0 entries'),
        infoFiltered: fmt(_('(filtered from %(max)s total entries)'), { max: '_MAX_' }),
        zeroRecords: _('No matching records found'),
        emptyTable: _('No data available in table')
    };
}

/**
 * Point the template-rendered <ol-pagination> at the DataTable's paging state.
 * @param {object} table - DataTables API instance for #editions
 */
function initPagination(table) {
    const wrapper = document.getElementById('editions-pagination');
    if (!wrapper) {
        return;
    }
    const pagination = wrapper.querySelector('ol-pagination');

    // Attributes rather than properties, so the values survive if the custom
    // element hasn't upgraded yet.
    function syncPagination() {
        const info = table.page.info();
        pagination.setAttribute('total-pages', info.pages);
        pagination.setAttribute('current-page', info.page + 1);
        wrapper.hidden = info.pages < 2;
    }

    pagination.addEventListener('ol-pagination-change', function (e) {
        // The component renders anchors; cancelling keeps paging client-side.
        e.preventDefault();
        table.page(e.detail.page - 1).draw('page');
    });
    $('#editions').on('draw.dt', syncPagination);
    // The initializing draw already happened by the time we get here.
    syncPagination();
}

export function initEditionsTable() {
    let currentLength;
    // Prevent reinitialization of the editions datatable
    if ($.fn.DataTable.isDataTable($('#editions'))) {
        return;
    }
    $('#editions th.title').on('mouseover', function () {
        if ($(this).hasClass('sorting_asc')) {
            $(this).attr('title', _('Sort latest to earliest'));
        } else if ($(this).hasClass('sorting_desc')) {
            $(this).attr('title', _('Sort earliest to latest'));
        } else {
            $(this).attr('title', _('Sort by publish date'));
        }
    });
    $('#editions th.read').on('mouseover', function () {
        if ($(this).hasClass('sorting_asc')) {
            $(this).attr('title', _('Push readable versions to the bottom'));
        } else if ($(this).hasClass('sorting_desc')) {
            $(this).attr('title', _('Sort by editions to read'));
        } else {
            $(this).attr('title', _('Available to read'));
        }
    });

    $('#editions').on('length.dt', function (e, settings, length) {
        localStorage.setItem(LS_RESULTS_LENGTH_KEY, length);
    });

    const rowCount = $('#editions tbody tr').length;
    if (rowCount < 4) {
        $('#editions').DataTable({
            aoColumns: [{ sType: 'html' }, null],
            order: [[1, 'asc']],
            bPaginate: false,
            bInfo: false,
            bFilter: false,
            bStateSave: false,
            bAutoWidth: false,
            language: datatablesLanguage()
        });
    } else {
        currentLength = Number(localStorage.getItem(LS_RESULTS_LENGTH_KEY));
        const table = $('#editions').DataTable({
            aoColumns: [{ sType: 'html' }, null],
            order: [[1, 'asc']],
            lengthMenu: [
                [3, 10, 25, 50, 100, -1],
                [3, 10, 25, 50, 100, _('All')]
            ],
            dom: DATATABLES_DOM,
            bPaginate: true,
            bInfo: true,
            bFilter: true,
            bStateSave: false,
            bAutoWidth: false,
            language: datatablesLanguage(),
            pageLength: currentLength ? currentLength : DEFAULT_LENGTH,
            drawCallback: function () {
                // A jQuery object is always truthy, so check its length for the toolbar's presence.
                if ($('#ile-toolbar').length) {
                    // `ile-items` is unset until the first ILE selection is made.
                    const editionStorage = JSON.parse(sessionStorage.getItem('ile-items') || '{}').edition || [];
                    const matchEdition = string => {
                        return string.match(/OL[0-9]+[a-zA-Z]/);
                    };
                    for (const el of $('.ile-selected')) {
                        const anchor = el.getElementsByTagName('a');
                        if (anchor.length) {
                            const edIdentifier = matchEdition(anchor[0].getAttribute('href'));
                            if (!editionStorage.includes(edIdentifier[0])) {
                                el.classList.remove('ile-selected');
                            }
                        }
                    }
                    for (const el of $('.ile-selectable')) {
                        const anchor = el.getElementsByTagName('a');
                        if (anchor.length) {
                            const edIdentifier = matchEdition(anchor[0].getAttribute('href'));
                            if (editionStorage.includes(edIdentifier[0])) {
                                el.classList.add('ile-selected');
                            }
                        }
                    }
                }
            }
        });
        initPagination(table);
    }
}
