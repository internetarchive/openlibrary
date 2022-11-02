/**
 * Adds listeners to each given check-in component.
 *
 * @param {HTMLCollection<HTMLElement>} elems
 */
export function initCheckInForms(elems) {
    for (const elem of elems) {
        const closeButton = elem.querySelector('.check-in__cancel-btn')
        closeButton.addEventListener('click', function() {
            closeDialog(elem.dataset.modalRef)
        })

        const submitButton = elem.querySelector('.check-in__submit-btn')
        submitButton.addEventListener('click', function(event) {
            event.preventDefault()
            submitEvent(elem)
        })

        const yearSelect = elem.querySelector('select[name=year]')
        yearSelect.addEventListener('change', function(event) {
            onYearChange(elem, event.target.value)
        })

        const monthSelect = elem.querySelector('select[name=month]')
        monthSelect.addEventListener('change', function(event) {
            onMonthChange(elem, event.target.value)
        })
    }
}

/**
 * Sets the date selectors of the given form to the given year, month, and day.
 *
 * @param {HTMLElement} parentElement The root element of the check-in component
 * @param {Number} year Four digit year
 * @param {Number} month One-indexed month
 * @param {Number} day The day
 */
export function setDate(parentElement, year, month, day) {
    const yearSelect = parentElement.querySelector('select[name=year]')
    const monthSelect = parentElement.querySelector('select[name=month]')
    const daySelect = parentElement.querySelector('select[name=day]')
    const submitButton = parentElement.querySelector('.check-in__submit-btn')

    yearSelect.value = year
    monthSelect.value = month
    daySelect.value = day

    let daysInMonth = DAYS_IN_MONTH[month - 1]
    if (month === 2 && isLeapYear(year)) {
        ++daysInMonth
    }

    toggleDayVisibility(daySelect, daysInMonth)

    monthSelect.disabled = false
    daySelect.disabled = false
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

const DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

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

    const editionField = elem.querySelector('#edition-key')
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
        day: day ? Number(day) : null
    }

    if (editionKey) {
        data.edition_key = editionKey
    }

    // TODO: Validate data

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
        success: function() {
            resetSelects(elem.querySelectorAll('select'))
            closeDialog(elem.dataset.modalRef)
        }
    });
}

/**
 * Sets all given `select` elements to the default value.
 *
 * @param {HTMLCollection<HTMLSelectElement>} selects
 */
function resetSelects(selects) {
    for (const select of selects) {
        select.value = ''
        if (select.name !== 'year') {
            select.disabled = true
        }
    }
}

/**
 * Dispatches close dialog event to the parent dialog element.
 *
 * @param {string} id Unique identifier for the parent dialog element
 */
function closeDialog(id) {
    const dialog = document.querySelector(`#${id}`)
    dialog.dispatchEvent(new Event('close-dialog'))
}
