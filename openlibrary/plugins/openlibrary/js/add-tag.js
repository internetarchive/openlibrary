import { websafe } from './jsdef'

export function initAddTagImport () {
    const nameField = document.querySelector('#tag_name');
    const descriptionField = document.querySelector('#tag_description')
    var tagSelect = document.querySelector('#tag_type');
    var tagType = tagSelect.options[tagSelect.selectedIndex].text;
    const button = document.querySelector('#create-tag-button')

    // button.addEventListener('click', function(event){
    //     // if form is valid:
    //     if (nameField.checkValidity()) {
    //         // prevent default button behavior
    //         event.preventDefault()

    //         // Make call to create list
    //         const data = {
    //             name: websafe(nameField.value),
    //             description: websafe(descriptionField.value),
    //             type: websafe(tagType)
    //         }

    //         const successCallback = function() {
    //             return
    //         }

    //         createTag(data, successCallback)
    //     }
    // })
}

/**
 * Makes a POST to a `.json` endpoint.
 * @param {object} data Configurations and payload for POST request.
 */
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


export function createTag(data, success) {
    post({
        url: '/tag.json',
        data: data,
        success: function(resp) {
            success(resp.key, data.name)
        }
    });
}
