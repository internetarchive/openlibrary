export function initDialogs(elems) {
    for (const elem of elems) {
        const closeButton = elem.querySelector('.close-dialog-btn')
        closeButton.addEventListener('click', function() {
            closeDialog(elem)
        })
        const submitButton = elem.querySelector('.submit-dialog-btn')
        submitButton.addEventListener('click', function(event) {
            event.preventDefault()
            submitEvent(elem)
        })
        elem.addEventListener('click', function(event) {

            // Event target exclusions needed for FireFox, which sets mouse positions to zero on
            // <select> and <option> clicks
            if (isOutOfBounds(event, elem) && event.target.nodeName !== 'SELECT' && event.target.nodeName !== 'OPTION') {
                closeDialog(elem)
            }
        })
    }
}

function submitEvent(elem) {
    const eventType = Number(elem.dataset.eventType)
    const url = elem.querySelector('form').action

    const editionField = elem.querySelector('#edition-key')
    const editionKey = editionField ? editionField.value : null

    const startDayField = elem.querySelector('select[name=start_day]')
    const startDay = startDayField.value
    const startMonthField = elem.querySelector('select[name=start_month]')
    const startMonth = startMonthField.value
    const startYearField = elem.querySelector('select[name=start_year]')
    const startYear = startYearField.value

    const endDayField = elem.querySelector('select[name=end_day]')
    const endDay = endDayField.value
    const endMonthField = elem.querySelector('select[name=end_month]')
    const endMonth = endMonthField.value
    const endYearField = elem.querySelector('select[name=end_year]')
    const endYear = endYearField.value

    const data = {event_type: Number(eventType)}
    if (eventType !== 1) {
        data.end_day = endDay ? Number(endDay) : null
        data.end_month = endMonth ? Number(endMonth) : null
        data.end_year = endYear ? Number(endYear) : null
    } else {
        data.start_day = startDay ? Number(startDay) : null,
        data.start_month = startMonth ? Number(startMonth) : null,
        data.start_year = startYear ? Number(startYear) : null
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
    }
}

function closeDialog(dialog) {
    dialog.close()
    const endDateElem = dialog.querySelector('.end-date')
    const startDateElem = dialog.querySelector('.start-date')
    endDateElem.classList.add('hidden')
    startDateElem.classList.add('hidden')
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
