
function post(data) {
    $.ajax({
        type: 'POST',
        url: data.url,
        contentType: 'application/json',
        data: JSON.stringify(data.data),
        dataType: 'json',

        beforeSend: function(xhr) {
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.setRequestHeader('Accept', 'application/json');
        },
        success: data.success,
        complete: data.complete
    });
}

export function createList(userKey, data, success) {
    post({
        url: `${userKey}/lists.json`,
        data: data,
        success: function(resp) {
            success(resp.key, data.name)
        }
    });
}

export function addToList(listKey, seed, success) {
    post({
        url: `${listKey}/seeds.json`,
        data: { add: [seed] },
        success: success
    });
}

export function removeFromList(listKey, seed, success) {
    post({
        url: `${listKey}/seeds.json`,
        data: { remove: [seed] },
        success: success
    });
}

export function updateReadingLog(formElem, success) {
    const formData = new FormData(formElem)

    $.ajax({
        type: 'POST',
        url: formElem.getAttribute('action'),
        data: formData,
        processData: false,
        contentType: false,
        success: success
    })
}
