import 'datatables.net-dt';
import '../../../../../static/css/legacy-datatables.less';

const DEFAULT_LENGTH = 3;
const LS_RESULTS_LENGTH_KEY = 'editions-table.resultsLength';

export function initEditionsTable() {
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
    $('#editions th.read span').html('&nbsp;&uarr;');
    $('#editions th').on('mouseup', function(){
        $('#editions th span').html('');
        $(this).find('span').html('&nbsp;&uarr;');
        if ($(this).hasClass('sorting_asc')) {
            $(this).find('span').html('&nbsp;&darr;');
        } else if ($(this).hasClass('sorting_desc')) {
            $(this).find('span').html('&nbsp;&uarr;');
        }
    });

    $('#editions').on('length.dt', function(e, settings, length) {
        localStorage.setItem(LS_RESULTS_LENGTH_KEY, length);
    });

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
