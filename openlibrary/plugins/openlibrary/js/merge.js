export function initAuthorMergePage() {
    $('#save').click(function () {
        const n = $('#mergeForm input[type=radio]:checked').length;
        if (n === 0) {
            $('#noMaster').dialog('open');
        } else {
            $('#confirmMerge').dialog('open');
        }
        return false;
    });
    $('div.radio:first input[type=radio]').prop('checked', true);
    $('div.checkbox:first input[type=checkbox]').prop('checked', true);
    $('div.author:first').addClass('master');
    $('#include input[type=radio]').mouseover(function () {
        $(this).parent().parent().addClass('mouseoverHighlight', 300);
    });
    $('#include input[type=radio]').mouseout(function () {
        $(this).parent().parent().removeClass('mouseoverHighlight', 100);
    });
    $('#include input[type=radio]').click(function () {
        const previousMaster = $('.merge').find('div.master');
        previousMaster.removeClass('master mergeSelection');
        previousMaster.find('input[type=checkbox]').prop('checked', false);
        $(this).parent().parent().addClass('master');
        $(this).parent().parent().find('input[type=checkbox]').prop('checked', true);
    });
    $('#include input[type=checkbox]').on('change', function () {
        if (!$(this).parent().parent().hasClass('master')) {
            if ($(this).is(':checked')) {
                $(this).parent().parent().addClass('mergeSelection');
            } else {
                $(this).parent().parent().removeClass('mergeSelection');
            }
        }
    });
}
