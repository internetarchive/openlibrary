
/**
 * a confirm dialog for confirming actions
 * @this jQuery.Object
 * @param {Function} callback
 * @param {Object} options
 * @return {jQuery.Object}
 */
export function confirmDialog(callback, options) {
    var _this = this;
    var defaults = {
        autoOpen: false,
        width: 400,
        modal: true,
        resizable: false,
        buttons: {
            'Yes, I\'m sure': function() {
                callback.apply(_this);
            },
            'No, cancel': function() {
                $(_this).dialog('close');
            }
        }
    };
    options = $.extend(defaults, options);
    return this.dialog(options);
}

/**
 * Wires up confirmation prompts.
 * In future this will be generalised.
 * @return {Function} for creating a confirm dialog
 */
function initConfirmationDialogs() {
    const CONFIRMATION_PROMPT_DEFAULTS = { autoOpen: false, modal: true };
    $('#noMaster').dialog(CONFIRMATION_PROMPT_DEFAULTS);
    $('#confirmMerge').dialog(
        $.extend({}, CONFIRMATION_PROMPT_DEFAULTS, {
            buttons: {
                'Yes, Merge': function() {
                    $('#mergeForm').trigger('submit');
                    $(this).parents().find('button').attr('disabled','disabled');
                },
                'No, Cancel': function() {
                    $(this).dialog('close');
                }
            }
        })
    );
    $('#leave-waitinglist-dialog').dialog(
        $.extend({}, CONFIRMATION_PROMPT_DEFAULTS, {
            width: 450,
            resizable: false,
            buttons: {
                'Yes, I\'m sure': function() {
                    $(this).dialog('close');
                    $(this).data('origin').closest('td').find('form').trigger('submit');
                },
                'No, cancel': function() {
                    $(this).dialog('close');
                }
            }
        })
    );
}

/**
 * Wires up dialog close buttons
 * If an element has the class dialog--open it will trigger the
 * opening of a dialog. The `aria-controls` attribute on that same element
 * communicates where the HTML of that dialog lives.
 */
export function initDialogs() {
    $('.dialog--open').on('click', function () {
        const $link = $(this),
            href = `#${$link.attr('aria-controls')}`;

        $link.colorbox({ inline: true, opacity: '0.5', href,
            maxWidth: '640px', width: '100%' });
    });
    initConfirmationDialogs();

    // This will close the dialog in the current page.
    $('.dialog--close').attr('href', 'javascript:;').on('click', () => $.fn.colorbox.close());
    // This will close the colorbox from the parent.
    $('.dialog--close-parent').on('click', () => parent.$.fn.colorbox.close());
}
