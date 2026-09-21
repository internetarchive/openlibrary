import $ from 'jquery';
import 'jquery-colorbox';
import { olConfirm } from '../../../../components/lit/alert-dialog.js';
import { FadingToast } from '../Toast.js';
import '../../../../../static/css/components/metadata-form.css';



/**
 * Initializes share popover button listeners.
 *
 * <ol-popover> manages its own open/close lifecycle on trigger click, so
 * Colorbox wiring is no longer needed.
 */
export function initShareModal() {
    addShareModalButtonListeners();
}

/**
 * Adds click listeners to action buttons inside share popovers.
 */
function addShareModalButtonListeners() {
    $(document).on('click', '.share-popover .copy-url-btn', async function(event) {
        event.preventDefault();
        try {
            await navigator.clipboard.writeText(window.location.href);
            const msg = this.dataset.copyToast || 'URL copied to clipboard';
            showComponentToast(msg, 'success');
        } catch {
            // Fallback for non-secure contexts or permission denied
        }
        const popover = this.closest('ol-popover');
        if (popover) {
            popover.open = false;
        }
    });

    $(document).on('click', '.share-popover .embed-work-btn', function(event) {
        event.preventDefault();
        const embedCode = this.dataset.embedCode;
        if (embedCode) {
            const promptMsg = this.dataset.embedPrompt || 'Copy embed code to clipboard:';
            prompt(promptMsg, embedCode);
        }
        const popover = this.closest('ol-popover');
        if (popover) {
            popover.open = false;
        }
    });

    $(document).on('click', '.share-popover .share-popover__link:not(.embed-work-btn):not(.copy-url-btn)', function() {
        const popover = this.closest('ol-popover');
        if (popover) {
            popover.open = false;
        }
    });
}


/** English fallbacks. Must match type/edition/notes_modal_i18n.html. */
export const DEFAULT_NOTES_MODAL_STRINGS = {
    saveError: 'Could not save your note. Please try again.',
    deleteError: 'Could not delete your note. Please try again.',
    deleteTitle: 'Delete this note?',
    deleteMessage: 'This cannot be undone.',
    deleteConfirm: 'Delete Note',
    cancel: 'Cancel',
    close: 'Close',
};

/**
 * Reads the server-rendered translations off the dialog's data-i18n attribute.
 * Falls back to English if the attribute is missing or malformed.
 *
 * @param {HTMLElement} el Element carrying the data-i18n attribute.
 * @returns {Object} Translated strings merged over the English defaults.
 */
export function notesModalStrings(el) {
    try {
        const raw = el?.dataset?.i18n;
        if (raw) {
            return { ...DEFAULT_NOTES_MODAL_STRINGS, ...JSON.parse(raw) };
        }
    } catch {
        // Malformed attribute: fall through to the English defaults.
    }
    return DEFAULT_NOTES_MODAL_STRINGS;
}

/**
 * Shows an <ol-toast>. Built by hand rather than through showToast(), whose
 * import would re-run customElements.define() from a second bundle and pull Lit
 * in — same workaround as templates/design/components/toast.html.jinja.
 *
 * @param {String} message Already-translated message text.
 * @param {String} type 'success' or 'error'.
 */
function showComponentToast(message, type) {
    let region = document.querySelector('ol-toast-region');
    if (!region) {
        region = document.createElement('ol-toast-region');
        document.body.appendChild(region);
    }
    const toast = document.createElement('ol-toast');
    toast.setAttribute('message', message);
    toast.setAttribute('type', type);
    region.appendChild(toast);
}

/**
 * Wires up the book notes dialog. One dialog per page (NotesModalDialog.html),
 * one trigger link per sidebar (desktop and mobile), so every link opens it.
 *
 * @param {NodeList} modalLinks Notes trigger links on the page.
 */
export function initNotesModal(modalLinks) {
    const dialog = document.querySelector('.js-notes-modal');
    if (!dialog) {
        return;
    }

    const strings = notesModalStrings(dialog);
    const form = dialog.querySelector('.book-notes-form');
    const textarea = form.querySelector('.notes-modal-textarea');
    const deleteButton = dialog.querySelector('.js-notes-modal-delete');
    const saveButton = dialog.querySelector('.js-notes-modal-save');

    /**
     * The sidebar link is rendered with the note's state baked in (see
     * databarWork.html), so a save or delete has to move both copies of it --
     * desktop and mobile -- or they stay stale until the next page load.
     */
    function setNoteIndicator(hasNote) {
        modalLinks.forEach((link) => {
            link.classList.toggle('icon-link--has-note', hasNote);
            const use = link.querySelector('svg use');
            if (use) {
                const [sprite] = use.getAttribute('href').split('#');
                use.setAttribute('href', `${sprite}#icon-sticky-note${hasNote ? '-text' : ''}`);
            }
        });
    }

    // Which request is in flight, if any: 'save' | 'delete' | null.
    let pending = null;

    /**
     * Save needs text in the field, and neither button may fire while the
     * other's request is in flight: both post to the same endpoint, so the
     * delete could land before the save it was meant to follow.
     */
    function syncButtons() {
        saveButton.loading = pending === 'save';
        deleteButton.loading = pending === 'delete';
        saveButton.disabled = pending === 'delete' || !textarea.value.trim();
        deleteButton.disabled = pending === 'save';
    }

    // work_id travels in the URL, not the body, so it is dropped from the form
    // data before posting.
    async function postNote(formData) {
        const workOlid = formData.get('work_id');
        formData.delete('work_id');
        const response = await fetch(`/works/${workOlid}/notes.json`, {
            method: 'POST',
            body: formData,
        });
        if (!response.ok) {
            throw new Error(`Notes request failed: ${response.status}`);
        }
    }

    async function saveNote() {
        // Guards the function itself rather than trusting the button's state:
        // ol-button blocks a real pointer while loading, but the listener is on
        // the host, so a synthetic or keyboard-driven click still arrives here.
        if (pending || !textarea.value.trim()) {
            return;
        }
        pending = 'save';
        syncButtons();
        try {
            await postNote(new FormData(form));
            dialog.open = false;
            deleteButton.classList.remove('hidden');
            setNoteIndicator(true);
        } catch {
            // Leave the dialog open so the patron does not lose the note.
            showComponentToast(strings.saveError, 'error');
        } finally {
            pending = null;
            syncButtons();
        }
    }

    // The endpoint removes the note when no `notes` field is sent.
    async function deleteNote() {
        if (pending) {
            return;
        }
        const formData = new FormData(form);
        formData.delete('notes');
        pending = 'delete';
        syncButtons();
        try {
            await postNote(formData);
            // Close like a save does: the note this was opened to edit is gone.
            // The reset still happens, for the next time it opens.
            dialog.open = false;
            textarea.value = '';
            deleteButton.classList.add('hidden');
            setNoteIndicator(false);
        } catch {
            showComponentToast(strings.deleteError, 'error');
        } finally {
            pending = null;
            syncButtons();
        }
    }

    // The dialog is rendered once and reused, so the button state is set now and
    // kept in step with the field rather than assumed on each open.
    textarea.addEventListener('input', syncButtons);
    syncButtons();

    modalLinks.forEach((link) => {
        link.addEventListener('click', () => {
            dialog.open = true;
        });
    });

    saveButton.addEventListener('click', saveNote);

    deleteButton.addEventListener('click', async() => {
        const confirmed = await olConfirm({
            title: strings.deleteTitle,
            message: strings.deleteMessage,
            confirmLabel: strings.deleteConfirm,
            cancelLabel: strings.cancel,
            labelClose: strings.close,
            destructive: true,
        });
        if (confirmed) {
            await deleteNote();
        }
    });
}

/**
* Add listeners to update and delete buttons on the notes page.
*
* On successful delete, list elements related to the note are removedd
* from the view.
*/
export function addNotesPageButtonListeners() {
    $('.update-note-link-button').on('click', function(event) {
        event.preventDefault();
        const workId = $(this).parent().siblings('input')[0].value;
        const editionId = $(this).parent().attr('id').split('-')[0];
        const note = $(this).parent().siblings('textarea')[0].value;

        const formData = new FormData();
        formData.append('notes', note);
        formData.append('edition_id', `OL${editionId}M`);

        $.ajax({
            url: `/works/OL${workId}W/notes.json`,
            data: formData,
            type: 'POST',
            contentType: false,
            processData: false,
            success: function() {
                showToast('Update successful!');
            }
        });
    });

    $('.delete-note-button').on('click', function() {
        if (confirm('Really delete this book note?')) {
            const $parent = $(this).parent();

            const workId = $(this).parent().siblings('input')[0].value;
            const editionId = $(this).parent().attr('id').split('-')[0];

            const formData = new FormData();
            formData.append('edition_id', `OL${editionId}M`);

            $.ajax({
                url: `/works/OL${workId}W/notes.json`,
                data: formData,
                type: 'POST',
                contentType: false,
                processData: false,
                success: function() {
                    showToast('Note deleted.');

                    // Remove list element from UI:
                    if ($parent.closest('.notes-list').children().length === 1) {
                        // This is the last edition for a set of notes on a work.
                        // Remove the work element:
                        $parent.closest('.main-list-item').remove();

                        if (!$('.main-list-item').length) {
                            $('.list-container')[0].innerText = 'No notes found.';
                        }
                    } else {
                        // Notes for other editions of the work exist
                        // Remove the edition's notes list item:
                        $parent.closest('.notes-list-item').remove();
                    }
                }
            });
        }
    });
}

/**
 * Creates and displays a toast component.
 *
 * @param {String} message Message displayed in toast component
 * @param {JQuery} $parent Mount point for toast component
 */
function showToast(message, $parent) {
    new FadingToast(message, $parent).show();
}

/**
 * Initializes a collection of observations modals.
 *
 * Adds on click listeners to all given modal links, and adds change listeners to
 * each modal's inputs.
 *
 * @param {JQuery} $modalLinks  A collection of observations modal links.
 */
export function initObservationsModal($modalLinks) {
    addClickListeners($modalLinks, '800px');
    addObservationReloadListeners($('.observations-list'));
    addDeleteObservationsListeners($('.delete-observations-button'));

    $modalLinks.each(function(_i, modalLinkElement) {
        const $element = $(modalLinkElement);
        const context = JSON.parse(getModalContent($element).dataset['context']);

        addObservationChangeListeners($element.next(), context);
    });
}

/**
 * Add on click listeners to a collection of modal links.
 *
 * When any of the links are clicked, it's corresponding modal
 * will be displayed.
 *
 * @param {JQuery} $modalLinks  A collection of modal links.
 */
function addClickListeners($modalLinks, maxWidth) {
    $modalLinks.each(function(_i, modalLinkElement) {
        $(modalLinkElement).on('click', function() {
            // Get context, which is attached to the modal content
            const content = getModalContent($(this));
            displayModal(content, maxWidth);
        });
    });
}

/**
 * Gets reference to modal content that is associated with the
 * given modal link.
 *
 * @param {JQuery} $modalLink Link that triggers a modal
 * @returns {HTMLElement}  Reference to a modal's content
 */
function getModalContent($modalLink) {
    return $modalLink.siblings()[0].children[0];
}

/**
 * Adds listeners to all observation lists on a page.
 *
 * Observation lists are found in the aggregate observations
 * view, and display all observations that were submitted for
 * a work. If new observations are submitted, an 'observationReload'
 * event is fired, triggering an update of the observations list.
 *
 * @param {JQuery} $observationLists All of the observations lists on a page
 */
function addObservationReloadListeners($observationLists) {
    $observationLists.each(function(_i, list) {
        $(list).on('contentReload', function() {
            const $list = $(this);
            const $buttonsDiv = $list.siblings('div').first();
            const id = $list.attr('id');
            const workOlid = `OL${id.split('-')[0]}W`;

            $list.empty();
            $list.append(`
                <li class="throbber-li">
                    <div class="throbber"><h3>Updating observations</h3></div>
                </li>
            `);

            $.ajax({
                type: 'GET',
                url: `/works/${workOlid}/observations`,
                dataType: 'json'
            })
                .done(function(data) {
                    let listItems = '';
                    for (const [category, values] of Object.entries(data)) {
                        let observations = values.join(', ');
                        observations = observations.charAt(0).toUpperCase() + observations.slice(1);

                        listItems += `
                    <li>
                        <span class="observation-category">${category.charAt(0).toUpperCase() + category.slice(1)}:</span> ${observations}
                    </li>
                `;
                    }

                    $list.empty();

                    if (listItems.length === 0) {
                        listItems = `
                    <li>
                        No observations for this work.
                    </li>
                `;
                        $list.addClass('no-content');
                        $buttonsDiv.removeClass('observation-buttons');
                        $buttonsDiv.addClass('no-content');
                        $buttonsDiv.children().first().addClass('hidden');
                    } else {
                        $list.removeClass('no-content');
                        $buttonsDiv.removeClass('no-content');
                        $buttonsDiv.addClass('observation-buttons');
                        $buttonsDiv.children().first().removeClass('hidden');
                    }

                    $list.append(listItems);
                });
        });
    });
}

/**
 * Deletes all of a work's observations and refreshes observations view.
 *
 * Delete observation buttons are only available on the aggregate
 * observations view, beneath a list of previously submitted observations.
 * Clicking the delete button will delete all of the observations for a
 * work and update the view.
 *
 * @param {JQuery} $deleteButtons All observation delete buttons found on a page.
 */
function addDeleteObservationsListeners($deleteButtons) {
    $deleteButtons.each(function(_i, deleteButton) {
        const $button = $(deleteButton);

        $button.on('click', function() {
            const workOlid = `OL${$button.prop('id').split('-')[0]}W`;

            $.ajax({
                url: `/works/${workOlid}/observations`,
                type: 'DELETE',
                contentType: 'application/json',
                success: function() {
                    // Remove observations in view
                    const $observationsView = $button.closest('.observation-view');
                    const $list = $observationsView.find('ul');

                    $list.empty();
                    $list.append(`
                        <li>
                            No observations for this work.
                        </li>
                    `);
                    $list.addClass('no-content');

                    $button.parent().removeClass('observation-buttons');
                    $button.parent().addClass('no-content');
                    $button.addClass('hidden');

                    // find and clear modal selections
                    clearForm($button.siblings().find('form'));
                }
            });
        });
    });
}

/**
 * Unchecks all inputs in an observations modal form.
 *
 * @param {JQuery} $form An observations modal form
 */
function clearForm($form) {
    $form.find('input').each(function(_i, input) {
        if (input.checked) {
            input.checked = false;
        }
    });
}

/**
 * Displays a model identified by the given identifier.
 *
 * Optionally fires a reload event to a list with the given ID.
 *
 * @param {HTMLElement} content  Content that will be displayed in the modal
 * @param {String} maxWidth  The max width of the modal
 */
function displayModal(content, maxWidth) {
    const modalId = `#${content.id}`;
    const context = content.dataset['context'] ? JSON.parse(content.dataset['context']) : null;
    const reloadId = context ? context.reloadId : null;

    $.colorbox({
        inline: true,
        opacity: '0.5',
        href: modalId,
        width: '100%',
        maxWidth: maxWidth,
        onClosed: function() {
            if (reloadId) {
                $(`#${reloadId}`).trigger('contentReload');
            }
        }
    });
}

/**
 * Adds change listeners to each input in the observations section of the modal.
 *
 * For each checkbox and radio button in the observations form, a change listener
 * that triggers observation submissions is added.  On change, a payload containing
 * the username, action type ('add' when an input is checked, 'delete' when unchecked),
 * and observation type and value are sent to the back-end server.
 *
 * @param {JQuery}  $parent  Object that contains the observations form.
 * @param {Object}  context  An object containing the patron's username and the work's OLID.
 */
function addObservationChangeListeners($parent, context) {
    const $questionSections = $parent.find('.aspect-section');
    const username = context.username;
    const workOlid = context.work.split('/')[2];

    $questionSections.each(function() {
        const $inputs = $(this).find('input');

        $inputs.each(function() {
            $(this).on('change', function() {
                const type = $(this).attr('name');
                const value = $(this).attr('value');
                const observation = {};
                observation[type] = value;

                const data = {
                    username: username,
                    action: `${$(this).prop('checked') ? 'add': 'delete'}`,
                    observation: observation
                };

                submitObservation($(this), workOlid, data, type);
            });
        });
    });
}

/**
 * Submits an observation to the server.
 *
 * @param {String}  workOlid    The OLID for the work being observed.
 * @param {Object}  data        Payload that will be sent to the back-end server.
 * @param {String}  sectionType Name of the input's section.
 */
function submitObservation($input, workOlid, data, sectionType) {
    let toastMessage;
    const capitalizedType = sectionType[0].toUpperCase() + sectionType.substring(1);

    // Make AJAX call
    $.ajax({
        type: 'POST',
        url: `/works/${workOlid}/observations`,
        contentType: 'application/json',
        data: JSON.stringify(data)
    })
        .done(function() {
            toastMessage = `${capitalizedType} saved!`;
        })
        .fail(function() {
            toastMessage = `${capitalizedType} save failed...`;
        })
        .always(function() {
            showToast(toastMessage, $input.closest('.metadata-form'));
        });
}
