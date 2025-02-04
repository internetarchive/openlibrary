/**
 * Defines code needed for reading log check-in UI components.
 * @module check-ins/index
 */
import { PersistentToast } from '../Toast'
import { initDialogs } from '../native-dialog'

/**
 * Enum for check-in event types.
 * @readonly
 * @enum {string}
 */
export const CheckInEvent = {
    /** Started reading */
    START: '1',
    /** Update to an existing check-in event */
    UPDATE: '2',
    /** Completed reading */
    FINISH: '3'
}

/**
 * Array of days for each month, listed in order starting with January.
 * Assumes that it is not a leap year.
 */
const DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

/**
 * Adds listeners to each given check-in component.
 *
 * @param {HTMLCollection<HTMLElement>} elems
 */
export function initCheckInForms(elems) {
    for (const elem of elems) {
        const idField = elem.querySelector('input[name=event_id]')

        const deleteButton = elem.querySelector('.check-in__delete-btn')
        deleteButton.addEventListener('click', function(event) {
            event.preventDefault()
            deleteEvent(elem, elem.dataset.workOlid, idField.value)
        })

        const submitButton = elem.querySelector('.check-in__submit-btn')
        submitButton.addEventListener('click', function(event) {
            event.preventDefault()
            submitEvent(elem)
        })

        const yearSelect = elem.querySelector('select[name=year]')
        const currentYear = new Date().getFullYear();
        const hiddenYear = yearSelect.querySelector('.show-if-local-year')

        // The year selector has a hidden option for next year.  This option is
        // shown on 1 January if the client's local year is different from
        // the server's local year.
        if (Number(hiddenYear.value) === currentYear) {
            hiddenYear.classList.remove('hidden')
        }
        yearSelect.addEventListener('change', function(event) {
            onYearChange(elem, event.target.value)
        })

        const monthSelect = elem.querySelector('select[name=month]')
        monthSelect.addEventListener('change', function(event) {
            onMonthChange(elem, event.target.value)
        })

        const todayLink = elem.querySelector('.check-in__today')
        todayLink.addEventListener('click', function() {
            onTodayClick(elem)
        })
    }
}

/**
 * Adds listeners to check-in date prompts.
 *
 * @param {HTMLCollection<HTMLElement>} elems Components that prompt for check-in dates
 */
export function initCheckInPrompts(elems) {
    for (const elem of elems) {
        const workOlid = elem.dataset.workOlid
        const modal = document.querySelector(`#check-in-dialog-${workOlid}`)

        const todayLink = elem.querySelector('.prompt-today')
        todayLink.addEventListener('click', function() {
            onTodayClick(modal, true)
        })

        const customDateLink = elem.querySelector('.prompt-custom')
        customDateLink.addEventListener('click', function() {
            modal.showModal()
        })

        const yearLink = elem.querySelector('.prompt-current-year')
        yearLink.addEventListener('click', function() {
            onYearClick(modal)
        })
    }
}

/**
 * Enables edit date functionality.
 *
 * @param {HTMLElement} elems Edit date buttons
 */
export function initCheckInEdits(elems) {
    for (const elem of elems) {
        elem.addEventListener('click', function() {
            const workOlid = elem.dataset.workOlid
            const modal = document.querySelector(`#check-in-dialog-${workOlid}`)
            modal.showModal()
        })
    }
}

/**
 * Sets check-in form inputs to today's date.
 *
 * Optionally submits form upon setting date.
 *
 * @param {HTMLElement} modal Element containing the check-in form
 * @param {boolean} doSubmit Submits form if true
 */
function onTodayClick(modal, doSubmit=false) {
    const now = new Date()
    const year = now.getFullYear()
    const month = now.getMonth() + 1
    const day = now.getDate()

    setDate(modal, year, month, day)
    if (doSubmit) {
        submitEvent(modal.querySelector('.check-in'))
    }
}

function onYearClick(modal) {
    const year = new Date().getFullYear()
    setDate(modal, year)
    submitEvent(modal.querySelector('.check-in'))
}

/**
 * Sets the date selectors of the given form to the given year, month, and day.
 *
 * @param {HTMLElement} parentElement The root element of the check-in component
 * @param {Number} year Four digit year
 * @param {Number|null} month One-indexed month
 * @param {Number|null} day The day
 */
export function setDate(parentElement, year, month=null, day=null) {
    const yearSelect = parentElement.querySelector('select[name=year]')
    const monthSelect = parentElement.querySelector('select[name=month]')
    const daySelect = parentElement.querySelector('select[name=day]')
    const submitButton = parentElement.querySelector('.check-in__submit-btn')

    yearSelect.value = year
    monthSelect.value = month ? month : ''
    daySelect.value = day ? day : ''

    let daysInMonth = DAYS_IN_MONTH[month - 1]
    if (month === 2 && isLeapYear(year)) {
        ++daysInMonth
    }

    toggleDayVisibility(daySelect, daysInMonth)

    monthSelect.disabled = false
    daySelect.disabled = day ? false : true
    submitButton.disabled = false
}

/**
 * Adjusts available options when a new year is selected.
 *
 * If no year is given, the submit button is disabled and month and year selectors
 * are reset and disabled.  Otherwise, the month selector and submit button are enabled.
 *
 * In the event that the year changes to or from a leap year and February is the selected month,
 * the amount of days are adjusted.
 *
 * @param {HTMLElement} parentElement The root element of the check-in component
 * @param {string} value The value of the selected year option
 */
function onYearChange(parentElement, value) {
    const monthSelect = parentElement.querySelector('select[name=month]')
    const daySelect = parentElement.querySelector('select[name=day]')
    const submitButton = parentElement.querySelector('.check-in__submit-btn')

    if (value) {
        monthSelect.disabled = false
        submitButton.disabled = false

        // Adjust for leap years:
        if (monthSelect.value === '2') {
            if (isLeapYear(Number(value))) {
                daySelect.options[29].classList.remove('hidden')
            } else {
                daySelect.options[29].classList.add('hidden')
                if (daySelect.value === '29') {
                    daySelect.value = '28'
                }
            }
        }
    } else {
        daySelect.value = ''
        daySelect.disabled = true
        monthSelect.value = ''
        monthSelect.disabled = true
        submitButton.disabled = true
    }
}

/**
 * Adjusts available options when a new month is selected.
 *
 * Disables and resets day select element if no month is selected.
 * Otherwise, enables day selector and ensures that the correct number
 * of day options are present.
 *
 * @param {HTMLElement} parentElement The root element of the check-in component
 * @param {string} value The value of the selected option
 */
function onMonthChange(parentElement, value) {
    const daySelect = parentElement.querySelector('select[name=day]')

    if (value) {
        const yearSelect = parentElement.querySelector('select[name=year]')
        const year = Number(yearSelect.value)
        const month = Number(value)
        let days = DAYS_IN_MONTH[month - 1]
        if (month === 2 && isLeapYear(year)) {
            ++days
        }

        toggleDayVisibility(daySelect, days)

        daySelect.disabled = false
    } else {
        daySelect.value = ''
        daySelect.disabled = true
    }
}

/**
 * Hides day options that are greater than the number of days in the month.
 *
 * The day `select` element is rendered with 32 `option` elements:
 * Days 1 through 31, and a default option. This function adds the `hidden`
 * class to any day options that are not available for the currently selected
 * month.
 *
 * @param {HTMLSelectElement} daySelect
 * @param {Number} daysInMonth Number of days in the selected month
 */
function toggleDayVisibility(daySelect, daysInMonth) {
    for (let i = 0; i < daySelect.options.length; ++i) {
        if (i <= daysInMonth) {
            daySelect.options[i].classList.remove('hidden')
        } else {
            daySelect.options[i].classList.add('hidden')
        }
    }
}

/**
 * Determines if the given year is a leap year.
 *
 * @param {Number} year
 * @returns `true` if the given year is a leap year.
 */
function isLeapYear(year) {
    return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0)
}

/**
 * Posts check-in event to the server.
 *
 * @param {HTMLElement} elem The root element of the check-in component
 */
function submitEvent(elem) {
    const eventType = Number(elem.dataset.eventType)
    const url = elem.querySelector('form').action

    const idField = elem.querySelector('input[name=event_id]')
    const id = idField.value

    const editionField = elem.querySelector('input[name=edition_key]')
    const editionKey = editionField ? editionField.value : null

    const dayField = elem.querySelector('select[name=day]')
    const day = dayField.value
    const monthField = elem.querySelector('select[name=month]')
    const month = monthField.value
    const yearField = elem.querySelector('select[name=year]')
    const year = yearField.value

    const data = {
        event_type: Number(eventType),
        year: year ? Number(year) : null,
        month: month ? Number(month) : null,
        day: day ? Number(day) : null,
        event_id: id ? Number(id) : null
    }

    if (editionKey) {
        data.edition_key = editionKey
    }

    $.ajax({
        type: 'POST',
        url: url,
        contentType: 'application/json',
        data: JSON.stringify(data),
        dataType: 'json',
        beforeSend: function(xhr) {
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.setRequestHeader('Accept', 'application/json');
        },
        success: function(data) {
            idField.value = data.id
            showDateView(elem.dataset.workOlid, year, month, day)
            const deleteButton = elem.querySelector('.check-in__delete-btn')
            deleteButton.classList.remove('invisible')
        },
        error: function() {
            new PersistentToast('Failed to submit check-in.  Please try again in a few moments.').show()
        },
        complete: function() {
            closeDialog(elem.dataset.workOlid)
        }
    });
}

/**
 * Dispatches close dialog event to the parent dialog element.
 *
 * @param {string} workOlid Uniquely identifies a check-in dialog element.
 */
function closeDialog(workOlid) {
    const dialog = document.querySelector(`#check-in-dialog-${workOlid}`)
    dialog.dispatchEvent(new Event('close-dialog'))
}

/**
 * Updates and displays check-in date view.
 *
 * Hides check-in prompt component.
 *
 * @param {string} workOlid ID used to identify related components
 * @param {str} year Check-in event year
 * @param {str|null} month Check-in event month
 * @param {str|null} day Check-in event day
 */
function showDateView(workOlid, year, month, day) {
    let date = year
    if (month) {
        date += `-${month.padStart(2, '0')}`
        if (day) {
            date += `-${day.padStart(2, '0')}`
        }
    }
    const displayElement = document.querySelector(`#check-in-display-${workOlid}`)
    const dateField = displayElement.querySelector('.check-in-date')
    dateField.textContent = date

    const promptElem = document.querySelector(`#prompt-${workOlid}`)
    promptElem.classList.add('hidden')

    displayElement.classList.remove('hidden')
}

/**
 * Hides date display element and shows date prompt element.
 *
 * @param {string} workOlid Part of unique identifier for check-in UI components
 */
function showDatePromptView(workOlid) {
    const promptElem = document.querySelector(`#prompt-${workOlid}`)
    const displayElement = document.querySelector(`#check-in-display-${workOlid}`)
    displayElement.classList.add('hidden')
    promptElem.classList.remove('hidden')
}

/**
 * Deletes record with given event ID, and updates view.
 *
 * @param {HTMLElement} rootElem Root element of check-in form.
 * @param {string} workOlid Uniquely identifies check-in components
 * @param {string} eventId ID of event that is being deleted
 */
function deleteEvent(rootElem, workOlid, eventId) {
    $.ajax({
        type: 'DELETE',
        url: `/check-ins/${eventId}`,
        success: function() {
            const idField = rootElem.querySelector('input[name=event_id]')
            idField.value = ''
            showDatePromptView(workOlid)
            const deleteButton = rootElem.querySelector('.check-in__delete-btn')
            deleteButton.classList.add('invisible')
        },
        error: function() {
            new PersistentToast('Failed to delete check-in.  Please try again in a few moments.').show()
        },
        complete: function() {
            closeDialog(workOlid)
        }
    });
}

/**
 * Adds listener to open reading goal modal.
 *
 * Updates yearly goal form's current year to the patron's
 * local year.
 *
 * @param {HTMLCollection<HTMLElement>} links Prompts for adding a reading goal
 */
export function initYearlyGoalPrompt(links) {
    const yearlyGoalModal = document.querySelector('#yearly-goal-modal')

    for (const link of links) {
        link.addEventListener('click', function() {
            yearlyGoalModal.showModal()
        })
    }
}

/**
 * Updates year to the client's local year.
 *
 * Used to display the correct local year on 1 January.
 *
 * Elements passed to this function are expected to have a
 * `data-server-year` attribute, which is set to the server's
 * local year.
 *
 * @param {HTMLCollection<HTMLElement>} elems ELements which display only the current year
 */
export function displayLocalYear(elems) {
    const localYear = new Date().getFullYear()
    for (const elem of elems) {
        const serverYear = Number(elem.dataset.serverYear)
        if (localYear !== serverYear) {
            elem.textContent = localYear
        }
    }
}

/**
 * Adds click listeners to the given edit goal links.
 *
 * @param {HTMLCollection<HTMLElement>} editLinks Edit goal links
 */
export function initGoalEditLinks(editLinks) {
    for (const link of editLinks) {
        const parent = link.closest('.reading-goal-progress')
        const modal = parent.querySelector('dialog')
        addGoalEditClickListener(link, modal)
    }
}

/**
 * Adds click listener to the given edit link.
 *
 * Given modal will be displayed when the edit link
 * is clicked.
 * @param {HTMLElement} editLink An edit goal link
 * @param {HTMLDialogElement} modal The modal that will be shown
 */
function addGoalEditClickListener(editLink, modal) {
    editLink.addEventListener('click', function() {
        modal.showModal()
    })
}

/**
 * Adds click listeners to given collection of goal submission
 * buttons.
 *
 * @param {HTMLCollection<HTMLElement>} submitButtons Submit goal buttons
 */
export function initGoalSubmitButtons(submitButtons) {
    for (const button of submitButtons) {
        addGoalSubmissionListener(button)
    }
}

/**
 * Adds click listener to given reading goal form submission button.
 *
 * On click, POSTs form to server.  Updates view depending on whether
 * the action set a new goal, or updated an existing goal.
 * @param {HTMLELement} submitButton Reading goal form submit button
 */
function addGoalSubmissionListener(submitButton) {
    submitButton.addEventListener('click', function(event) {
        event.preventDefault()

        const form = submitButton.closest('form')

        if (!form.checkValidity()) {
            form.reportValidity()
            throw new Error('Form invalid')
        }
        const formData = new FormData(form)

        fetch(form.action, {
            method: 'POST',
            headers: {
                'content-type': 'application/x-www-form-urlencoded'
            },
            body: new URLSearchParams(formData)
        })
            .then((response) => {
                if (!response.ok) {
                    throw new Error('Failed to set reading goal')
                }
                const modal = form.closest('dialog')
                if (modal) {
                    modal.close()
                }

                const yearlyGoalSection = modal.closest('.yearly-goal-section')
                if (formData.get('is_update')) {  // Progress component exists on page
                    const goalInput = form.querySelector('input[name=goal]')
                    const isDeleted = Number(goalInput.value) === 0

                    if (isDeleted) {
                        const chipGroup = yearlyGoalSection.querySelector('.chip-group')
                        const goalContainer = yearlyGoalSection.querySelector('#reading-goal-container')
                        if (chipGroup) {
                            chipGroup.classList.remove('hidden')
                        }
                        if (goalContainer) {
                            goalContainer.remove()
                        }
                    } else {
                        const progressComponent = modal.closest('.reading-goal-progress')
                        updateProgressComponent(progressComponent, Number(formData.get('goal')))
                    }
                } else {
                    const goalYear = formData.get('year')
                    fetchProgressAndUpdateView(yearlyGoalSection, goalYear)
                    const banner = document.querySelector('.page-banner-mybooks')
                    if (banner) {
                        banner.remove()
                    }
                }
            })
    })
}

/**
 * Updates given reading goal progress component with a new
 * goal.
 *
 * @param {HTMLElement} elem A reading goal progress component
 * @param {Number} goal The new reading goal
 */
function updateProgressComponent(elem, goal) {
    // Calculate new percentage:
    const booksReadSpan = elem.querySelector('.reading-goal-progress__books-read')
    const booksRead = Number(booksReadSpan.textContent)
    const percentComplete = Math.floor((booksRead / goal) * 100)

    // Update view:
    const goalSpan = elem.querySelector('.reading-goal-progress__goal')
    const completedBar = elem.querySelector('.reading-goal-progress__completed')
    goalSpan.textContent = goal
    completedBar.style.width = `${Math.min(100, percentComplete)}%`
}

/**
 * Fetches and displays progress component.
 *
 * Adds listeners to the progress component, and hides
 * link for setting reading goal.
 *
 * @param {HTMLElement} yearlyGoalElem Container for progress component and reading goal link.
 * @param {string} goalYear Year that the goal is set for.
 */
function fetchProgressAndUpdateView(yearlyGoalElem, goalYear) {
    fetch(`/reading-goal/partials.json?year=${goalYear}`)
        .then((response) => {
            if (!response.ok) {
                throw new Error('Failed to fetch progress element')
            }
            return response.json()
        })
        .then(function(data) {
            const html = data['partials']
            const progress = document.createElement('SPAN')
            progress.id = 'reading-goal-container'
            progress.innerHTML = html
            yearlyGoalElem.appendChild(progress)

            // Hide the "Set 20XX reading goal" link:
            yearlyGoalElem.children[0].classList.add('hidden')

            const progressEditLink = progress.querySelector('.edit-reading-goal-link')
            const updateModal = progress.querySelector('dialog')
            initDialogs([updateModal])
            addGoalEditClickListener(progressEditLink, updateModal)
            const submitButton = updateModal.querySelector('.reading-goal-submit-button')
            addGoalSubmissionListener(submitButton)
        })
}
