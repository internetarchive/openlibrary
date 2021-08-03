import { ajax } from 'jquery';

export function deleteObservation(type, value, workKey, username) {
    const data = constructDataObject(type, value, username, 'delete');
    ajax({
        type: 'POST',
        url: `${workKey}/observations`,
        contentType: 'application/json',
        data: JSON.stringify(data)
    })
}

export function addObservation(type, value, workKey, username) {
    const data = constructDataObject(type, value, username, 'add');
    ajax({
        type: 'POST',
        url: `${workKey}/observations`,
        contentType: 'application/json',
        data: JSON.stringify(data)
    })
}

function constructDataObject(type, value, username, action) {
    const data = {
        username: username,
        action: action,
        observation: {}
    }

    data.observation[type.toLowerCase()] = value.toLowerCase();

    return data;
}
