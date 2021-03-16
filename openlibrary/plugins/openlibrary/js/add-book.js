export function initAddBookImport () {
    window.q.push(function() {
        $('.list-books a').click(function() {
            var li = $(this).parents('li:first');
            var attributeId = li.attr('id');
            $('input#work').val('/works/' + $(attributeId));
            $('form#addbook').submit();
        });
        $('#bookAddCont').click(function() {
            $('input#work').val('none-of-these');
            $('form#addbook').submit();
        });
    });
}
