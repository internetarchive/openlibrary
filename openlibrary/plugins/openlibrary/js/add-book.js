export function initAddBookImport () {
    window.q.push(function() {
        $('.list-books a').click(function() {
            var li = $(this).parents('li:first');
            $('input#work').val(`/works/${li.attr('id')}`);
            $('form#addbook').submit();
        });
        $('#bookAddCont').click(function() {
            $('input#work').val('none-of-these');
            $('form#addbook').submit();
        });
    });
}
