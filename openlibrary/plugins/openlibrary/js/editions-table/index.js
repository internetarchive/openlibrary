import './jquery.dataTables';
import '../../../../../static/css/legacy-datatables.less';

export function initEditionsTable() {
    var rowCount;
    $('#editions span.count').each(function(i){
        var myLength = $(this).text().length;
        $(this).text(i+1);
        if (myLength == 1) {
            $(this).prepend('000');
        } else if (myLength == 2) {
            $(this).prepend('00');
        } else if (myLength == 3) {
            $(this).prepend('0');
        }
    });
    $('#editions th.title').mouseover(function(){
        if ($(this).hasClass('sorting_asc')) {
            $(this).attr('title','Sort latest to earliest');
        } else if ($(this).hasClass('sorting_desc')) {
            $(this).attr('title','Sort earliest to latest');
        } else {
            $(this).attr('title','Sort by publish date');
        }
    });
    $('#editions th.read').mouseover(function(){
        if ($(this).hasClass('sorting_asc')) {
            $(this).attr('title','Push readable versions to the bottom');
        } else if ($(this).hasClass('sorting_desc')) {
            $(this).attr('title','Sort by editions to read');
        } else {
            $(this).attr('title','Available to read');
        }
    });
    $('#editions th.locate').mouseover(function(){
        if ($(this).hasClass('sorting_asc')) {
            $(this).attr('title','Are you a member of your local library?');
        } else if ($(this).hasClass('sorting_desc')) {
            $(this).attr('title','Sory by books likely to be at libraries near you');
        } else {
            $(this).attr('title','Locate this book');
        }
    });
    $('#editions th.buy').mouseover(function(){
        if ($(this).hasClass('sorting_asc')) {
            $(this).attr('title','Books for sale to the bottom');
        } else if ($(this).hasClass('sorting_desc')) {
            $(this).attr('title','Bring books for sale to the top');
        } else {
            $(this).attr('title','Available to buy');
        }
    });
    $('#editions th.read span').html('&nbsp;&uarr;');
    $('#editions th').mouseup(function(){
        $('#editions th span').html('');
        $(this).find('span').html('&nbsp;&uarr;');
        if ($(this).hasClass('sorting_asc')) {
            $(this).find('span').html('&nbsp;&darr;');
        } else if ($(this).hasClass('sorting_desc')) {
            $(this).find('span').html('&nbsp;&uarr;');
        }
    });
    rowCount = $('#editions tbody tr').length;
    if (rowCount < 16) {
        $('#editions').dataTable({
            'aoColumns': [{'sType':'html'},null,null,null],
            'aaSorting': [ [1,'asc'] ],
            'bPaginate': false,
            'bInfo': false,
            'bFilter': false,
            'bStateSave': false,
            'bAutoWidth': false
        });
    } else {
        $('#editions').dataTable({
            'aoColumns': [{'sType':'html'},null,null,null],
            'aaSorting': [ [1,'asc'] ],
            'bPaginate': true,
            'bInfo': true,
            'sPaginationType': 'full_numbers',
            'bFilter': false,
            'bStateSave': false,
            'bAutoWidth': false
        });
    }
    $('.return-book').submit(function(event) {
        if (!confirm('Really return this book?')) {
            event.preventDefault();
        }
    });
}
