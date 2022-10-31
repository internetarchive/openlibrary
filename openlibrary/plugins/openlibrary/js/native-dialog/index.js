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
