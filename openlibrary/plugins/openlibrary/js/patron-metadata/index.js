import '../../../../../static/css/components/metadata-form.less';

const OBSERVATION_SUBMISSION = 'observationSubmission';
const ANY = 'allSections';

const SubmissionState = {
    INITIAL: 1,
    PENDING: 2,
    SUCCESS: 3,
    FAILURE: 4
};

export function initPatronMetadata() {
    function displayModal() {
        $.colorbox({
            inline: true,
            opacity: '0.5',
            href: '#metadata-form',
            width: '60%',
        });
    }

    function populateForm($form, observations, selectedValues) {
        let i18nStrings = JSON.parse(document.querySelector('#modal-link').dataset.i18n);
        for (const observation of observations) {
            let className = observation.multi_choice ? 'multi-choice' : 'single-choice';
            let $choices = $(`<div class="${className}"></div>`);
            let choiceIndex = observation.values.length;
            let type = observation.label;

            for (const value of observation.values) {
                let choiceId = `${type}Choice${choiceIndex--}`;
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
                                    <summary>${type}</summary>
                                    <div id="${type}-question">
                                        <h3>${observation.description}</h3>
                                        <span class="pending-indicator hidden"></span>
                                        <span class="success-indicator hidden">Selection saved!</span>
                                        <span class="failure-indicator hidden">Submission failed</span>
                                        ${$choices.prop('outerHTML')}
                                    </div>
                                </details>`);

            $formSection.on(OBSERVATION_SUBMISSION, function(event, sectionType, submissionState) {
                let pendingSpan = $(this).find('.pending-indicator')[0];
                let successSpan = $(this).find('.success-indicator')[0];
                let failureSpan = $(this).find('.failure-indicator')[0];

                if (sectionType === type || sectionType === ANY) {
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
                <a class="small dialog--close plain" href="javascript:;" id="cancel-submission">${i18nStrings.close_text}</a>
              </div>
            </div>`);

        addToggleListeners($('.aspect-section', $form));
    }

    $('#modal-link').on('click', function() {
        if ($('#user-metadata').children().length === 0) {
            let context = JSON.parse(document.querySelector('#modal-link').dataset.context);
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
                            populateForm($('#user-metadata'), data.observations, selectedValues);
                            addChangeListeners(context);
                            $('#cancel-submission').click(function() {
                                $.colorbox.close();
                            })
                            displayModal();
                        })
                        .fail(function() {
                            // TODO: Handle failed API calls gracefully.
                        })
                })
        } else {
            $('.aspect-section').trigger(OBSERVATION_SUBMISSION, [ANY, SubmissionState.INITIAL]);
            displayModal();
        }
    });
}

/**
 * Resizes modal when a details element is opened or closed.
 */
function toggleHandler() {
    let formHeight = $('#metadata-form').height();

    $('#cboxContent').height(formHeight + 22);
    $('#cboxLoadedContent').height(formHeight);
}

/**
 * Adds a toggle handler to all details elements.
 *
 * @param {JQuery} $toggleElements`Elements that will receive toggle handlers.
 */
function addToggleListeners($toggleElements) {
    $toggleElements.each(function() {
        $(this).on('toggle', toggleHandler);
    })
}


/**
 * TODO: documentation
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
 * TODO: documentation
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