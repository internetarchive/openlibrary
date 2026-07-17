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

    const $confirmMerge = $('#confirmMerge');
    if ($confirmMerge.length) {
        $confirmMerge.dialog(
            $.extend({}, CONFIRMATION_PROMPT_DEFAULTS, {
                buttons: {
                    'Yes, Merge': function() {
                        const commentInput = document.querySelector('#author-merge-comment');
                        if (commentInput.value) {
                            document.querySelector('#hidden-comment-input').value = commentInput.value;
                        }
                        $('#mergeForm').trigger('submit');
                        $(this).parents().find('button').attr('disabled', 'disabled');
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


/**
 * Collapses the search-inside form back to the button state.
 * @param {jQuery} $btnGroup - The .cta-button-group container.
 */
function collapseSearchForm($btnGroup) {
    $btnGroup.find('.search-inside-form').hide();
    $btnGroup.find('.search-inside-input').val('');
    $btnGroup.find('.preview-btn, .search-inside-trigger-btn').show();
    $btnGroup.find('[data-search-trigger]').attr('aria-expanded', 'false');
}

export function initPreviewDialogs() {
    // Delegated click handler for Book Preview buttons.
    // Uses event delegation so dynamically-added buttons (e.g. from
    // lazy-loaded carousels) work without re-initialization.
    $(document).off('click.bookPreview').on('click.bookPreview', '[data-book-preview]', function(e) {
        e.preventDefault();
        const $button = $(this);
        const dialog = document.getElementById('bookPreview');
        if (!dialog) return;

        const iframe = dialog.querySelector('iframe');
        if (iframe) {
            iframe.src = $button.data('iframe-src');
        }

        const link = dialog.querySelector('.learn-more a');
        if (link) {
            link.href = $button.data('iframe-link');
        }

        dialog.open = true;
    });

    $(document).off('ol-close.bookPreview').on('ol-close.bookPreview', '#bookPreview', function() {
        const iframe = this.querySelector('iframe');
        if (iframe) {
            iframe.src = '';
        }
    });

    // Handle clicking the "Search Inside" button to expand it to the input form
    $(document).off('click.bookSearchTrigger').on('click.bookSearchTrigger', '[data-search-trigger]', function(e) {
        e.preventDefault();
        const $triggerBtn = $(this);
        const $btnGroup = $triggerBtn.closest('.cta-button-group');
        $triggerBtn.attr('aria-expanded', 'true');
        $btnGroup.find('.preview-btn, .search-inside-trigger-btn').hide();
        $btnGroup.find('.search-inside-form').show().find('.search-inside-input').trigger('focus');
    });

    // Handle pressing Escape to collapse the search inside input form back
    $(document).off('keydown.bookSearchInput').on('keydown.bookSearchInput', '.search-inside-input', function(e) {
        if (e.key === 'Escape') {
            const $btnGroup = $(this).closest('.cta-button-group');
            collapseSearchForm($btnGroup);
            e.stopPropagation();
        }
    });

    // Handle clicking the cancel (&times;) button to collapse the form back
    $(document).off('click.bookSearchCancel').on('click.bookSearchCancel', '.search-cancel-btn', function(e) {
        e.preventDefault();
        collapseSearchForm($(this).closest('.cta-button-group'));
    });

    // Handle search form submission to open query inside preview dialog modal
    $(document).off('submit.bookSearchForm').on('submit.bookSearchForm', '.search-inside-form', function(e) {
        e.preventDefault();
        const $form = $(this);
        const query = $form.find('.search-inside-input').val();
        const ocaid = $form.data('ocaid');
        const dialog = document.getElementById('bookPreview');
        if (dialog) {
            const iframe = dialog.querySelector('iframe');
            if (iframe) {
                iframe.src = `https://archive.org/details/${ocaid}?view=theater&wrapper=false&q=${encodeURIComponent(query)}`;
            }
            const link = dialog.querySelector('.learn-more a');
            if (link) {
                link.href = `https://archive.org/details/${ocaid}`;
            }
            dialog.open = true;
        }
        collapseSearchForm($form.closest('.cta-button-group'));
    });
}

/**
 * Wires up dialog close buttons
 * If an element has the class dialog--open it will trigger the
 * opening of a dialog. The `aria-controls` attribute on that same element
 * communicates where the HTML of that dialog lives.
 */
export function initDialogs() {
    $('.dialog--open').on('click', function() {
        const $link = $(this),
            href = `#${$link.attr('aria-controls')}`;

        $link.colorbox({ inline: true, opacity: '0.5', href,
            maxWidth: '640px', width: '100%' });
    });

    initConfirmationDialogs();
    initPreviewDialogs();

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
        $(closer).on('click', () => $.fn.colorbox.close());
    });
}
