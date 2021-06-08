export function initAuthorMergePage() {
    $('#save').on('click', function () {
        const n = $('#mergeForm input[type=radio]:checked').length;
        if (n === 0) {
            $('#noMaster').dialog('open');
        } else {
            $('#confirmMerge').dialog('open');
        }
        return false;
    });
    $('div.radio').first().find('input[type=radio]').prop('checked', true);
    $('div.checkbox').first().find('input[type=checkbox]').prop('checked', true);
    $('div.author').first().addClass('master');
    $('#include input[type=radio]').on('mouseover', function () {
        $(this).parent().parent().addClass('mouseoverHighlight', 300);
    });
    $('#include input[type=radio]').on('mouseout', function () {
        $(this).parent().parent().removeClass('mouseoverHighlight', 100);
    });
    $('#include input[type=radio]').on('click', function () {
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

/**
 * Initializes preMerge element on author page.
 *
 * Show 'preMerge' element and launch author merge of duplicate keys into master key.
 * Assumes presence of element with '#preMerge' id and 'data-keys' attribute.
 */
export function initAuthorView() {
    const dataKeysJSON = $('#preMerge').data('keys');

    $('#preMerge').show();
    $('#preMerge').parent().show();

    let data = {
        master: dataKeysJSON['master'],
        duplicates: dataKeysJSON['duplicates']
    };

    $.ajax({
        url: '/authors/merge.json',
        type: 'POST',
        data: JSON.stringify(data),
        success: function() {
            $('#preMerge').fadeOut();
            $('#postMerge').fadeIn();
        },
        error: function() {
            $('#preMerge').fadeOut();
            $('#errorMerge').fadeIn();
        }
    });
}
