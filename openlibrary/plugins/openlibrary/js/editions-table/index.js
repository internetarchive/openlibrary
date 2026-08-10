import 'datatables.net-dt';
import '../../../../../static/css/legacy-datatables.css';

const DEFAULT_LENGTH = 3;
const LS_RESULTS_LENGTH_KEY = 'editions-table.resultsLength';
// DataTables' default layout ('lfrtip') minus 'p' — <ol-pagination> is the pager.
const DATATABLES_DOM = 'lfrti';

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

    pagination.addEventListener('ol-pagination-change', function(e) {
        // The component renders anchors; cancelling keeps paging client-side.
        e.preventDefault();
        table.page(e.detail.page - 1).draw('page');
    });
    $('#editions').on('draw.dt', syncPagination);
    // The initializing draw already happened by the time we get here.
    syncPagination();
}

export function initEditionsTable() {
    var rowCount;
    let currentLength;
    // Prevent reinitialization of the editions datatable
    if ($.fn.DataTable.isDataTable($('#editions'))) {
        return;
    }
    $('#editions th.title').on('mouseover', function(){
        if ($(this).hasClass('sorting_asc')) {
            $(this).attr('title', 'Sort latest to earliest');
        } else if ($(this).hasClass('sorting_desc')) {
            $(this).attr('title', 'Sort earliest to latest');
        } else {
            $(this).attr('title', 'Sort by publish date');
        }
    });
    $('#editions th.read').on('mouseover', function(){
        if ($(this).hasClass('sorting_asc')) {
            $(this).attr('title', 'Push readable versions to the bottom');
        } else if ($(this).hasClass('sorting_desc')) {
            $(this).attr('title', 'Sort by editions to read');
        } else {
            $(this).attr('title', 'Available to read');
        }
    });

    $('#editions').on('length.dt', function(e, settings, length) {
        localStorage.setItem(LS_RESULTS_LENGTH_KEY, length);
    });

    rowCount = $('#editions tbody tr').length;
    if (rowCount < 4) {
        $('#editions').DataTable({
            aoColumns: [{sType: 'html'}, null],
            order: [ [1, 'asc'] ],
            bPaginate: false,
            bInfo: false,
            bFilter: false,
            bStateSave: false,
            bAutoWidth: false
        });
    } else {
        currentLength = Number(localStorage.getItem(LS_RESULTS_LENGTH_KEY));
        const table = $('#editions').DataTable({
            aoColumns: [{sType: 'html'}, null],
            order: [ [1, 'asc'] ],
            lengthMenu: [ [3, 10, 25, 50, 100, -1], [3, 10, 25, 50, 100, 'All'] ],
            dom: DATATABLES_DOM,
            bPaginate: true,
            bInfo: true,
            bFilter: true,
            bStateSave: false,
            bAutoWidth: false,
            pageLength: currentLength ? currentLength : DEFAULT_LENGTH,
            drawCallback: function() {
                // A jQuery object is always truthy, so check its length for the toolbar's presence.
                if ($('#ile-toolbar').length) {
                    // `ile-items` is unset until the first ILE selection is made.
                    const editionStorage = JSON.parse(sessionStorage.getItem('ile-items') || '{}').edition || [];
                    const matchEdition = (string) => {
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
