import { Toast } from '../Toast.js';
import '../../../../../static/css/components/metadata-form.less';
import '../../../../../static/css/components/toast.less';

/**
 * Initializes a collection of notes modals.
 *
 * @param {JQuery} $modalLinks  A collection of notes modal links.
 */
export function initNotesModal($modalLinks) {
    addClickListeners($modalLinks);
    addNotesModalButtonListeners();
    addNotesReloadListeners($('.notes-textarea'));
}

/**
 * Adds click listeners to buttons in all notes modals on a page.
 */
function addNotesModalButtonListeners() {
    $('.update-note-button').on('click', function(){
        // Get form data
        const formData = new FormData($(this).prop('form'));

        if (formData.get('notes')) {
            const $deleteButton = $($(this).siblings()[0]);

            // Post data
            const workOlid = formData.get('work_id');
            formData.delete('work_id');

            $.ajax({
                url: `/works/${workOlid}/notes.json`,
                data: formData,
                type: 'POST',
                contentType: false,
                processData: false,
                success: function() {
                    showToast($('body'), 'Update successful!')
                    $.colorbox.close();
                    $deleteButton.removeClass('hidden');
                }
            });
        }
    });

    $('.delete-note-button').on('click', function() {
        const $button = $(this);

        // Get form data
        const formData = new FormData($button.prop('form'));

        // Post data
        const workOlid = formData.get('work_id');
        formData.delete('work_id');
        formData.delete('notes');

        $.ajax({
            url: `/works/${workOlid}/notes.json`,
            data: formData,
            type: 'POST',
            contentType: false,
            processData: false,
            success: function() {
                showToast($('body'), 'Note deleted.');
                $.colorbox.close();
                $button.toggleClass('hidden');
                $button.closest('form').find('textarea').val('');
            }
        });
    });
}

/**
* Add listeners to update and delete buttons on the notes page.
*
* On successful delete, list elements related to the note are removedd
* from the view.
*/
export function addNotesPageButtonListeners() {
    $('.update-note-button').on('click', function() {
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
                showToast($('body'), 'Update successful!')
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
                    showToast($('body'), 'Note deleted.');

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
 * Adds listeners for content reload events on a page's notes textareas
 *
 * When a registered textarea receives a content reload event, it's text
 * is updated with the most recently submitted note.
 *
 * @param {JQuery} $notesTextareas  All notes text areas on a page.
 */
function addNotesReloadListeners($notesTextareas) {
    $notesTextareas.each(function(_i, textarea) {
        const $textarea = $(textarea);

        $textarea.on('contentReload', function() {
            const newValue = $textarea.parent().find('.notes-modal-textarea')[0].value;
            $textarea.val(newValue);
        });
    });
}

/**
 * Creates and displays a toast component.
 *
 * @param {JQuery} $parent Mount point for toast component
 * @param {String} message Message displayed in toast component
 */
function showToast($parent, message) {
    new Toast($parent, message).show();
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
    addClickListeners($modalLinks);
    addObservationReloadListeners($('.observations-list'))
    addDeleteObservationsListeners($('.delete-observations-button'));

    $modalLinks.each(function(_i, modalLinkElement) {
        const $element = $(modalLinkElement);
        const context = $element.data('context');

        addObservationChangeListeners($element.next(), context);
    })
}

/**
 * Add on click listeners to a collection of modal links.
 *
 * When any of the links are clicked, it's corresponding modal
 * will be displayed.
 *
 * @param {JQuery} $modalLinks  A collection of modal links.
 */
function addClickListeners($modalLinks) {
    $modalLinks.each(function(_i, modalLinkElement) {
        $(modalLinkElement).on('click', function() {
            const context = $(this).data('context');
            displayModal(context.id, context.reloadId);
        })
    })
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
            `)

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
                })
        })
    })
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
                    `)
                    $list.addClass('no-content');

                    $button.parent().removeClass('observation-buttons');
                    $button.parent().addClass('no-content');
                    $button.addClass('hidden');

                    // find and clear modal selections
                    clearForm($button.siblings().find('form'));
                }
            });
        })
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
 * @param {String} modalId  A string that uniquely identifies a modal.
 * @param {String} [reloadId]   ID of list receiving a reload event
 */
function displayModal(modalId, reloadId) {
    $.colorbox({
        inline: true,
        opacity: '0.5',
        href: `#${modalId}-metadata-form`,
        width: '60%',
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
        const $inputs = $(this).find('input')

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
                }

                submitObservation($(this), workOlid, data, type);
            });
        })
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
    // Make AJAX call
    $.ajax({
        type: 'POST',
        url: `/works/${workOlid}/observations`,
        contentType: 'application/json',
        data: JSON.stringify(data)
    })
        .done(function() {
            toastMessage = `${sectionType} saved!`;
        })
        .fail(function() {
            toastMessage = `${sectionType} save failed...`;
        })
        .always(function() {
            showToast($input.closest('.metadata-form'), toastMessage);
        });
}
