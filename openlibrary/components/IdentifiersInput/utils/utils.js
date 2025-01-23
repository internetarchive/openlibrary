import {
    parseIsbn,
    parseLccn,
    isChecksumValidIsbn10,
    isChecksumValidIsbn13,
    isFormatValidIsbn10,
    isFormatValidIsbn13,
    isValidLccn,
} from '../../../plugins/openlibrary/js/idValidation.js';

export function errorDisplay(message, error_output) {
    let errorSelector;
    if (error_output === '#hiddenAuthorIdentifiers') {
        errorSelector = document.querySelector('#id-errors-author')
    } else if (error_output === '#hiddenWorkIdentifiers') {
        errorSelector = document.querySelector('#id-errors-work')
    } else if (error_output === '#hiddenEditionIdentifiers') {
        errorSelector = document.querySelector('#id-errors-edition')
    }
    if (message) {
        errorSelector.style.display = '';
        errorSelector.innerHTML = `<div>${message}</div>`;
    } else {
        errorSelector.style.display = 'none';
        errorSelector.innerHTML = '';
    }

}

function validateIsbn10(value) {
    const isbn10_value = parseIsbn(value);
    if (!isFormatValidIsbn10(isbn10_value)) {
        errorDisplay('ID must be exactly 10 characters [0-9] or X.', '#hiddenEditionIdentifiers');
        return false;
    } else if (
        isFormatValidIsbn10(isbn10_value) && !isChecksumValidIsbn10(isbn10_value)
    ) {
        errorDisplay(`ISBN ${isbn10_value} may be invalid. Please confirm if you'd like to add it before saving all changes`, '#hiddenEditionIdentifiers');
    }
    return true;
}

function validateIsbn13(value) {
    const isbn13_value = parseIsbn(value);

    if (!isFormatValidIsbn13(isbn13_value)) {
        errorDisplay('ID must be exactly 13 digits [0-9]. For example: 978-1-56619-909-4', '#hiddenEditionIdentifiers');
        return false;
    } else if (
        isFormatValidIsbn13(isbn13_value) && !isChecksumValidIsbn13(isbn13_value)
    ) {
        errorDisplay(`ISBN ${isbn13_value} may be invalid. Please confirm if you'd like to add it before saving all changes`, '#hiddenEditionIdentifiers');
    }
    return true;
}

function validateLccn(value) {
    const lccn_value = parseLccn(value);

    if (!isValidLccn(lccn_value)) {
        errorDisplay('Invalid ID format', '#hiddenEditionIdentifiers');
        return false;
    }
    return true;
}

export function validateIdentifiers(name, value, entries, error_output) {
    let validId = true;
    errorDisplay('', error_output);
    if (name === '' || name === '---') {
    // if somehow an invalid identifier is passed through
        errorDisplay('Invalid identifier', error_output);
        return false;
    }
    if (name === 'isbn_10') {
        validId = validateIsbn10(value);
    } else if (name === 'isbn_13') {
        validId = validateIsbn13(value);
    } else if (name === 'lccn') {
        validId = validateLccn(value);
    }
    if (Array.from(entries).some(entry => entry === value) === true) {
        validId = false;
        errorDisplay('That ID already exists for an identifier.', error_output);
    }
    return validId;
}
