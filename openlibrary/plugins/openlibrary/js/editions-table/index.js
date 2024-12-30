import 'datatables.net-dt';
import '../../../../../static/css/legacy-datatables.less';

const DEFAULT_LENGTH = 3;
const LS_RESULTS_LENGTH_KEY = 'editions-table.resultsLength';

export function initEditionsTable() {
    var rowCount;

    $('#editions th.title').on('mouseover', function(){
        if ($(this).hasClass('sorting_asc')) {
            $(this).attr('title','Sort latest to earliest');
        } else if ($(this).hasClass('sorting_desc')) {
            $(this).attr('title','Sort earliest to latest');
        } else {
            $(this).attr('title','Sort by publish date');
        }
    });
    $('#editions th.read').on('mouseover', function(){
        if ($(this).hasClass('sorting_asc')) {
            $(this).attr('title','Push readable versions to the bottom');
        } else if ($(this).hasClass('sorting_desc')) {
            $(this).attr('title','Sort by editions to read');
        } else {
            $(this).attr('title','Available to read');
        }
    });

    function toggleSorting(e) {
        $('#editions th span').html('');
        $(e).find('span').html('&nbsp;&uarr;');
        if ($(e).hasClass('sorting_asc')) {
            $(e).find('span').html('&nbsp;&darr;');
        } else if ($(e).hasClass('sorting_desc')) {
            $(e).find('span').html('&nbsp;&uarr;');
        }
    }

    $('#editions th.read span').html('&nbsp;&uarr;');
    $('#editions th').on('mouseup', function() {
        toggleSorting(this)
    });

    $('#editions').on('length.dt', function(e, settings, length) {
        togglePaginationVisibility(length);
        localStorage.setItem(LS_RESULTS_LENGTH_KEY, length);
    });

    $('#editions th').on('keydown', function(e) {
        if (e.key === 'Enter') {
            toggleSorting(this);
        }
    })

    rowCount = $('#editions tbody tr').length;
    const currentLength = Number(localStorage.getItem(LS_RESULTS_LENGTH_KEY)) || DEFAULT_LENGTH;

    $('#editions').DataTable({
        aoColumns: [{ sType: 'html' }, null],
        order: [[1, 'asc']],
        lengthMenu: [[3, 10, 25, 50, 100, -1], [3, 10, 25, 50, 100, 'All']],
        bPaginate: true, // Always allow pagination initially
        bInfo: true,
        sPaginationType: 'full_numbers',
        bFilter: true,
        bStateSave: false,
        bAutoWidth: false,
        pageLength: currentLength,
    });

    // Toggle pagination visibility based on row count and selected length
    function togglePaginationVisibility(selectedLength) {
        const paginationElement = $('.dataTables_paginate.paging_full_numbers');
        if (rowCount <= selectedLength || selectedLength === -1) {
            paginationElement.hide();
        } else {
            paginationElement.show();
        }
    }

    // Initial pagination visibility toggle
    togglePaginationVisibility(currentLength);
}
