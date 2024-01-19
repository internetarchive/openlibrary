import { declineRequest } from './merge-request-table/MergeRequestService';

export function initAuthorMergePage() {
    $('#save').on('click', function () {
        const n = $('#mergeForm input[type=radio]:checked').length;
        const confirmMergeButton = document.querySelector('#confirmMerge')
        if (n === 0) {
            $('#noMaster').dialog('open');
        } else if (confirmMergeButton) {
            $('#confirmMerge').dialog('open');
        } else {
            $('#mergeForm').trigger('submit')
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
    initRejectButton()
}

function initRejectButton() {
    const rejectButton = document.querySelector('#reject-author-merge-btn')
    if (rejectButton) {
        rejectButton.addEventListener('click', function() {
            rejectMerge()
            rejectButton.disabled = true
            const approveButton = document.querySelector('#save')
            approveButton.disabled = true
        })
    }
}

function rejectMerge() {
    const commentInput = document.querySelector('#author-merge-comment')
    const mridInput = document.querySelector('#mrid-input')
    declineRequest(Number(mridInput.value), commentInput.value)
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

    const data = {
        master: dataKeysJSON['master'],
        duplicates: dataKeysJSON['duplicates'],
        olids: dataKeysJSON['olids']
    };

    const mrid = dataKeysJSON['mrid']
    const comment = dataKeysJSON['comment']

    if (mrid) {
        data['mrid'] = mrid
    }
    if (comment) {
        data['comment'] = comment
    }

    $.ajax({
        url: '/authors/merge.json',
        type: 'POST',
        data: JSON.stringify(data),
        //jqXHR: JQueryXMLHttpRequest OBject, textStatus and errorThrown are both strings. 
        error: function(jqXHR, textStatus, errorThrown) {
            $('#preMerge').fadeOut();
            $('#errorMerge').fadeIn();
        },
        success: function(data,  textStatus, jqXHR) {
            $('#preMerge').fadeOut();
            $('#postMerge').fadeIn();
        }
    });
}
