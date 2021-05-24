import '../../../../../static/css/components/metadata-form.less';

// Event name for submission status updates:
const OBSERVATION_SUBMISSION = 'observationSubmission';

// Used to denote a submission state change for all sections:
const ANY_SECTION_TYPE = 'allSections';

// Denotes all possible states of an observation submission:
const SubmissionState = {
    INITIAL: 1, // Initial state --- nothing has been submitted yet.
    PENDING: 2, // A submission has been made, but the server has not yet responded.
    SUCCESS: 3, // The observation was successfully processed by the server.
    FAILURE: 4  // Something went wrong while the observation was being processed by the server.
};

export function initPatronMetadata() {
    function displayModal(id) {
        $.colorbox({
            inline: true,
            opacity: '0.5',
            href: `#${id}-metadata-form`,
            width: '60%',
        });
    }

    function populateForm($form, observations, selectedValues, id, i18nStrings) {
        for (const observation of observations) {
            let className = observation.multi_choice ? 'multi-choice' : 'single-choice';
            let $choices = $(`<div class="${className}"></div>`);
            let choiceIndex = observation.values.length;
            let type = observation.label;

            for (const value of observation.values) {
                let choiceId = `${id}-${observation.label}Choice${choiceIndex--}`;
                let checked = '';

                if (type in selectedValues
                    && selectedValues[type].includes(value)) {
                    checked = 'checked';
                }

                $choices.append(`
                <label for="${choiceId}" class="${className}-label">
                    <input type=${observation.multi_choice ? 'checkbox': 'radio'} name="${type}" id="${choiceId}" value="${value}" ${checked}>
                    ${value}
                </label>`);
            }

            let $formSection = $(`<details class="aspect-section" open>
                                    <summary><h3>${type}</h3></summary>
                                    <fieldset id="${id}-${type}-question">
                                        <legend>${observation.description}</legend>
                                        <span class="pending-indicator hidden"></span>
                                        <span class="success-indicator hidden">Selection saved!</span>
                                        <span class="failure-indicator hidden">Submission failed</span>
                                        ${$choices.prop('outerHTML')}
                                    </fieldset>
                                </details>`);

            /*
            Adds an observation submission state change event handler to this section of the form.

            The handler displays the appropriate submission state indicator depending on the given submission
            state.

            The handler takes a section type, which identifies which section's submission state should
            change, and the new submission state.
            */
            $formSection.on(OBSERVATION_SUBMISSION, function(event, sectionType, submissionState) {
                let pendingSpan = $(this).find('.pending-indicator')[0];
                let successSpan = $(this).find('.success-indicator')[0];
                let failureSpan = $(this).find('.failure-indicator')[0];

                if (sectionType === type || sectionType === ANY_SECTION_TYPE) {
                    switch (submissionState) {
                    case SubmissionState.INITIAL:
                        pendingSpan.classList.add('hidden');
                        successSpan.classList.add('hidden');
                        failureSpan.classList.add('hidden');
                        break;
                    case SubmissionState.PENDING:
                        pendingSpan.classList.remove('hidden');

                        successSpan.classList.add('hidden');
                        failureSpan.classList.add('hidden');
                        break;
                    case SubmissionState.SUCCESS:
                        successSpan.classList.remove('hidden');

                        pendingSpan.classList.add('hidden');
                        failureSpan.classList.add('hidden');
                        break;
                    case SubmissionState.FAILURE:
                        failureSpan.classList.remove('hidden');

                        pendingSpan.classList.add('hidden');
                        successSpan.classList.add('hidden');
                        break;
                    }
                }
            })

            $form.append($formSection);
        }
        $form.append(`
            <div class="formElement metadata-submit">
              <div class="form-buttons">
                <a class="small dialog--close plain" href="javascript:;" id="${id}-cancel-submission">${i18nStrings.close_text}</a>
              </div>
            </div>`);

        addToggleListeners($('.aspect-section', $form), id);
    }

    $('.modal-link').on('click', function() {
        let context = $(this).data('context');
        let i18nStrings = $(this).data('i18n');

        if ($(this).next().find(`#${context.id}-user-metadata`).children().length == 0) {
            let selectedValues = {};

            $.ajax({
                type: 'GET',
                url: `/works/${context.work.split('/')[2]}/observations`,
                dataType: 'json'
            })
                .done(function(data) {
                    selectedValues = data;

                    $.ajax({
                        type: 'GET',
                        url: '/observations',
                        dataType: 'json'
                    })
                        .done(function(data) {
                            populateForm($(`#${context.id}-user-metadata`), data.observations, selectedValues, context.id, i18nStrings);
                            addChangeListeners(context);
                            $(`#${context.id}-cancel-submission`).on('click', function() {
                                $.colorbox.close();
                            })
                            displayModal(context.id);
                        })
                        .fail(function() {
                            // TODO: Handle failed API calls gracefully.
                        })
                })
        } else {
            // Hide all submission state indicators when the modal is reopened:
            $('.aspect-section').trigger(OBSERVATION_SUBMISSION, [ANY_SECTION_TYPE, SubmissionState.INITIAL]);
            displayModal(context.id);
        }
    });
}

/**
 * Resizes modal when a details element is opened or closed.
 *
 * @param {Event} event Toggle event that triggered this handler.
 */
function toggleHandler(event) {
    let formHeight = $(`#${event.data.id}-metadata-form`).height();

    event.data.$element.closest('#cboxContent').height(formHeight + 22);
    event.data.$element.closest('#cboxLoadedContent').height(formHeight);
}

/**
 * Adds a toggle handler to all details elements.
 *
 * @param {JQuery} $toggleElements`Elements that will receive toggle handlers.
 */
function addToggleListeners($toggleElements, id) {
    $toggleElements.each(function() {
        $(this).on('toggle', {
            $element: $(this),
            id: id
        }, toggleHandler);
    })
}


/**
 * Adds change listeners to each input in the observations section of the modal.
 *
 * For each checkbox and radio button in the observations form, a change listener
 * that triggers observation submissions is added.  On change, a payload containing
 * the username, action type ('add' when an input is checked, 'delete' when unchecked),
 * and observation type and value are sent to the back-end server.
 *
 * @param {Object}  context  An object containing the patron's username and the work's OLID.
 */
function addChangeListeners(context) {
    let $questionSections = $('.aspect-section');
    let username = context.username;
    let workOlid = context.work.split('/')[2];

    $questionSections.each(function() {
        let $inputs = $(this).find('input')

        $inputs.each(function() {
            $(this).on('change', function() {
                let type = $(this).attr('name');
                let value = $(this).attr('value');
                let observation = {};
                observation[type] = value;

                let data = {
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
 * Submits an observation to the server and triggers submission status change events.
 *
 * @param {JQuery}  $input      The checkbox or radio button that is firing the change event.
 * @param {String}  workOlid    The OLID for the work being observed.
 * @param {Object}  data        Payload that will be sent to the back-end server.
 * @param {String}  sectionType Name of the input's section.
 */
function submitObservation($input, workOlid, data, sectionType) {
    // Show spinner:
    $input.trigger(OBSERVATION_SUBMISSION, [sectionType, SubmissionState.PENDING]);

    // Make AJAX call
    $.ajax({
        type: 'POST',
        url: `/works/${workOlid}/observations`,
        contentType: 'application/json',
        data: JSON.stringify(data)
    })
        .done(function() {
            // Show success message:
            $input.trigger(OBSERVATION_SUBMISSION, [sectionType, SubmissionState.SUCCESS]);
        })
        .fail(function() {
            // Show failure message:
            $input.trigger(OBSERVATION_SUBMISSION, [sectionType, SubmissionState.FAILURE]);
        });
}
