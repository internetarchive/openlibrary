export function initAddBookImport () {
    $('.list-books a').on('click', function() {
        var li = $(this).parents('li').first();
        $('input#work').val(`/works/${li.attr('id')}`);
        $('form#addbook').trigger('submit');
    });
    $('#bookAddCont').on('click', function() {
        $('input#work').val('none-of-these');
        $('form#addbook').trigger('submit');
    });
}
