export default function () {

    function val(selector) {
        return $.trim($(selector).val());
    }
    function error(message, event) {
        $('#errors').show().html(message);
        event.preventDefault();
    }

    // page may not be loaded via iframe
    if (parent && parent.closeThrobber) {
        parent.closeThrobber();
    }
    $('#form.addcover-form').on('submit', function(event) {
        var file = val('#coverFile');
        var url = val('#imageUrl');
        var coverid = val('#coverid');

        if (file === '' && (url === '' || url === 'http://') && coverid === '') {
            return error('Please choose an image or provide a URL.', event);
        }

        function test_url(url) {
            var obj = {
                optional: function() { return false; }
            }
            return $.validator.url.apply(obj, [url, null]);
        }

        if (url !== '' && url !== 'http://' && !test_url(url)) {
            return error('Please provide a valid URL.');
        }
    });

    // Clicking a cover should set the form value to the data-id of that cover
    $('#popcovers .book').on('click', function() {
        var coverid;
        $(this).toggleClass('selected').siblings().removeClass('selected');
        coverid = '';
        if ($(this).hasClass('selected')) {
            coverid = $(this).data('id');
        }
        $('#coverid').val(coverid);
    });

    // covers/manage.html
    $('.column').sortable({
        connectWith: '.trash'
    });
    $('.trash').sortable({
        connectWith: '.column'
    });
    $('.column').disableSelection();
    $('.trash').disableSelection();
    $('#topNotice').hide();
}
