import 'datatables.net-dt';
import '../../../../../static/css/legacy-datatables.less';

const DEFAULT_LENGTH = 3;
const LS_RESULTS_LENGTH_KEY = 'editions-table.resultsLength';

// Function to add the custom CSS for hiding pagination
function addCustomPaginationCSS() {
    const style = document.createElement('style');
    style.innerHTML = `
        .dataTables_paginate.paging_full_numbers:has(.paginate_button.previous.disabled):has(.paginate_button.next.disabled):has(.paginate_button.first.disabled):has(.paginate_button.last.disabled) {
            display: none;
        }
    `;
    document.head.appendChild(style);
}

export function initEditionsTable() {
    // Add the custom CSS for pagination
    addCustomPaginationCSS();

    var rowCount;
    let currentLength;

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
        localStorage.setItem(LS_RESULTS_LENGTH_KEY, length);
    });

    $('#editions th').on('keydown', function(e) {
        if (e.key === 'Enter') {
            toggleSorting(this);
        }
    })

    rowCount = $('#editions tbody tr').length;
    if (rowCount < 4) {
        $('#editions').DataTable({
            aoColumns: [{sType: 'html'},null],
            order: [ [1,'asc'] ],
            bPaginate: false,
            bInfo: false,
            bFilter: false,
            bStateSave: false,
            bAutoWidth: false
        });
    } else {
        currentLength = Number(localStorage.getItem(LS_RESULTS_LENGTH_KEY));
        $('#editions').DataTable({
            aoColumns: [{sType: 'html'},null],
            order: [ [1,'asc'] ],
            lengthMenu: [ [3, 10, 25, 50, 100, -1], [3, 10, 25, 50, 100, 'All'] ],
            bPaginate: true,
            bInfo: true,
            sPaginationType: 'full_numbers',
            bFilter: true,
            bStateSave: false,
            bAutoWidth: false,
            pageLength: currentLength ? currentLength : DEFAULT_LENGTH
        });
    }
}
