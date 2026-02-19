import 'jquery-ui/ui/widgets/dialog';
// For dialog boxes (e.g. add to list)
import 'jquery-colorbox';

/**
 * Wires up confirmation prompts.
 * In future this will be generalised.
 * @return {Function} for creating a confirm dialog
 */
function initConfirmationDialogs() {
    const CONFIRMATION_PROMPT_DEFAULTS = { autoOpen: false, modal: true };
    $('#noMaster').dialog(CONFIRMATION_PROMPT_DEFAULTS);

    const $confirmMerge = $('#confirmMerge')
    if ($confirmMerge.length) {
        $confirmMerge.dialog(
            $.extend({}, CONFIRMATION_PROMPT_DEFAULTS, {
                buttons: {
                    'Yes, Merge': function() {
                        const commentInput = document.querySelector('#author-merge-comment')
                        if (commentInput.value) {
                            document.querySelector('#hidden-comment-input').value = commentInput.value
                        }
                        $('#mergeForm').trigger('submit');
                        $(this).parents().find('button').attr('disabled','disabled');
                    },
                    'No, Cancel': function() {
                        $(this).dialog('close');
                    }
                }
            })
        );
    }
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


export function initPreviewDialogs() {
    // Colorbox modal + iframe for Book Preview Button
    const $buttons = $('.cta-btn--preview');
    $buttons.each((i, button) => {
        const $button = $(button);
        $button.colorbox({
            width: '100%',
            maxWidth: '640px',
            inline: true,
            opacity: '0.5',
            href: '#bookPreview',
            onOpen() {
                const $iframe = $('#bookPreview iframe');
                $iframe.prop('src', $button.data('iframe-src'));

                const $link = $('#bookPreview .learn-more a');
                $link[0].href = $button.data('iframe-link');
            },
            onCleanup() {
                $('#bookPreview iframe').prop('src', '');
            },
        });
    });
}

export function initBookTalkDialogs() {
    // Colorbox modal + iframe for Book Talk Watch Button, title, and cover image
    const $buttons = $('.cta-btn--watch[data-iframe-src], .book-talk-link[data-iframe-src]');
    $buttons.each((i, button) => {
        const $button = $(button);
        $button.colorbox({
            width: '100%',
            maxWidth: '800px',
            inline: true,
            opacity: '0.5',
            href: '#bookTalkPlayer',
            onOpen() {
                const $iframe = $('#bookTalkPlayer iframe');
                $iframe.prop('src', $button.data('iframe-src'));
                // Update modal title with the video title
                const title = $button.data('title');
                if (title) {
                    $('#bookTalkPlayer .book-talk-modal-title').text(title);
                }
            },
            onCleanup() {
                $('#bookTalkPlayer iframe').prop('src', '');
            },
        });
    });
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
    initPreviewDialogs();
    initBookTalkDialogs();

    // This will close the dialog in the current page.
    $('.dialog--close').attr('href', 'javascript:;').on('click', () => $.fn.colorbox.close());
    // This will close the colorbox from the parent.
    $('.dialog--close-parent').on('click', () => parent.$.fn.colorbox.close());
}

/**
 * Adds click listeners for closing dialogs to the given elements.
 *
 * @param {NodeList<Element>} closers
 */
export function initDialogClosers(closers) {
    closers.forEach(closer => {
        $(closer).on('click', () => $.fn.colorbox.close())
    })
}
