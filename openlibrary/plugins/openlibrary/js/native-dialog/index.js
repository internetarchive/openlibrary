export function initDialogs(elems) {
    for (const elem of elems) {
        const closeButton = elem.querySelector('.close-dialog-btn')
        closeButton.addEventListener('click', function() {
            closeDialog(elem)
        })
        elem.addEventListener('click', function(event) {

            // Event target exclusions needed for FireFox, which sets mouse positions to zero on
            // <select> and <option> clicks
            if (isOutOfBounds(event, elem) && event.target.nodeName !== 'SELECT' && event.target.nodeName !== 'OPTION') {
                closeDialog(elem)
            }
        })
        const submitButton = elem.querySelector('.submit-dialog-btn')
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

export function setDate(parentElement, year, month, day) {
    const yearSelect = parentElement.querySelector('select[name=year]')
    const monthSelect = parentElement.querySelector('select[name=month]')
    const daySelect = parentElement.querySelector('select[name=day]')
    const submitButton = parentElement.querySelector('.submit-dialog-btn')

    yearSelect.value = year
    monthSelect.value = month
    daySelect.value = day

    toggleDayVisibility(daySelect, DAYS_IN_MONTH[month - 1])

    monthSelect.disabled = false
    daySelect.disabled = false
    submitButton.disabled = false
}

function onYearChange(parentElement, value) {
    const monthSelect = parentElement.querySelector('select[name=month]')
    const daySelect = parentElement.querySelector('select[name=day]')
    const submitButton = parentElement.querySelector('.submit-dialog-btn')

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

function isLeapYear(year) {
    return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0)
}

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
            closeDialog(elem)
        }
    });
}

function resetSelects(selects) {
    for (const select of selects) {
        select.value = ''
        if (select.name !== 'year') {
            select.disabled = true
        }
    }
}

function closeDialog(dialog) {
    dialog.close()
}

function isOutOfBounds(event, dialog) {
    const rect = dialog.getBoundingClientRect()
    return (
        event.clientX < rect.left ||
        event.clientX > rect.right ||
        event.clientY < rect.top ||
        event.clientY > rect.bottom
    );
}
