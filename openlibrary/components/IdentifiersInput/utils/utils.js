import {
    parseIsbn,
    parseLccn,
    isChecksumValidIsbn10,
    isChecksumValidIsbn13,
    isFormatValidIsbn10,
    isFormatValidIsbn13,
    isValidLccn,
} from '../../../plugins/openlibrary/js/idValidation.js';

export function errorDisplay(message) {
    const errorSelector = document.querySelector('#id-errors');
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
        errorDisplay('ID must be exactly 10 characters [0-9] or X.');
        return false;
    } else if (isFormatValidIsbn10(isbn10_value) === true && isChecksumValidIsbn10(isbn10_value) === false) {
        errorDisplay(`ISBN ${isbn10_value} may be invalid. Please confirm if you'd like to add it before saving all changes`);
    }
    return true;
}

function validateIsbn13(value) {
    const isbn13_value = parseIsbn(value);

    if (!isFormatValidIsbn13(isbn13_value)) {
        errorDisplay('ID must be exactly 13 digits [0-9]. For example: 978-1-56619-909-4');
        return false;
    } else if (isFormatValidIsbn13(isbn13_value) === true && isChecksumValidIsbn13(isbn13_value) === false) {
        errorDisplay(`ISBN ${isbn13_value} may be invalid. Please confirm if you'd like to add it before saving all changes`);
    }
    return true;
}

function validateLccn(value) {
    const lccn_value = parseLccn(value);

    if (!isValidLccn(lccn_value)) {
        errorDisplay('Invalid ID format');
        return false;
    }
    return true;
}

export function validateEditionIdentifiers(name, value, entries) {
    let validId = true;
    errorDisplay('');
    if (name === '' || name === '---') {
    // if somehow an invalid identifier is passed through
        errorDisplay('Invalid identifier');
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
        errorDisplay('That ID already exists for this edition');
    }
    return validId;
}
