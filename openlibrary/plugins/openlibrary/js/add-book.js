import {
    parseIsbn,
    parseLccn,
    isChecksumValidIsbn10,
    isChecksumValidIsbn13,
    isFormatValidIsbn10,
    isFormatValidIsbn13,
    isValidLccn
} from './idValidation.js'
import { trimInputValues } from './utils.js';

let invalidChecksum;
let invalidIsbn10;
let invalidIsbn13;
let invalidLccn;
let emptyId;

const i18nStrings = JSON.parse(document.querySelector('form[name=edit]').dataset.i18n);
const addBookForm = $('form#addbook');

export function initAddBookImport () {
    $('.list-books a').on('click', function() {
        var li = $(this).parents('li').first();
        $('input#work').val(`/works/${li.attr('id')}`);
        addBookForm.trigger('submit');
    });
    $('#bookAddCont').on('click', function() {
        $('input#work').val('none-of-these');
        addBookForm.trigger('submit');
    });

    invalidChecksum = i18nStrings.invalid_checksum;
    invalidIsbn10 = i18nStrings.invalid_isbn10;
    invalidIsbn13 = i18nStrings.invalid_isbn13;
    invalidLccn = i18nStrings.invalid_lccn;
    emptyId = i18nStrings.empty_id;

    $('#id_value').on('change',autoCompleteIdName);
    $('#addbook').on('submit', parseAndValidateId);
    $('#id_value').on('input', clearErrors);
    $('#id_name').on('change', clearErrors);

    $('#publish_date').on('blur', validatePublishDate);

    trimInputValues('input')

    // Prevents submission if the publish date is > 1 year in the future
    addBookForm.on('submit', function() {
        if ($('#publish-date-errors').hasClass('hidden')) {
            return true;
        } else return false;
    })
}

// a flag to make raiseIsbnError perform differently upon subsequent calls
let addBookWithIsbnErrors = false;

function displayIsbnError(event, errorMessage) {
    if (!addBookWithIsbnErrors) {
        addBookWithIsbnErrors = true;
        const errorDiv = document.getElementById('id-errors');
        errorDiv.classList.remove('hidden');
        errorDiv.textContent = errorMessage;
        const confirm = document.getElementById('confirm-add');
        confirm.classList.remove('hidden');
        const isbnInput = document.getElementById('id_value');
        isbnInput.focus({focusVisible: true});
        event.preventDefault();
        return;
    }
    // parsing potentially invalid ISBN
    document.getElementById('id_value').value = parseIsbn(document.getElementById('id_value').value);
}

function displayLccnError(event, errorMessage) {
    const errorDiv = document.getElementById('id-errors');
    errorDiv.classList.remove('hidden');
    errorDiv.textContent = errorMessage;
    event.preventDefault();
    return;
}

function clearErrors() {
    addBookWithIsbnErrors = false;
    const errorDiv = document.getElementById('id-errors');
    errorDiv.classList.add('hidden');
    const confirm = document.getElementById('confirm-add');
    confirm.classList.add('hidden');
}

function parseAndValidateId(event) {
    const fieldName = document.getElementById('id_name').value;
    const idValue = document.getElementById('id_value').value;

    if (fieldName === 'isbn_10') {
        parseAndValidateIsbn10(event, idValue);
    }
    else if (fieldName === 'isbn_13') {
        parseAndValidateIsbn13(event, idValue);
    }
    else if (fieldName === 'lccn') {
        parseAndValidateLccn(event, idValue);
    }
    else if (!fieldName || !isEmptyId(event, idValue)) {
        document.getElementById('id_value').value = idValue.trim();
    }
}

function isEmptyId(event, idValue) {
    if (!idValue.trim()) {
        const errorDiv = document.getElementById('id-errors');
        errorDiv.classList.remove('hidden');
        errorDiv.textContent = emptyId;
        event.preventDefault();
        return true;
    }
    return false;
}

function parseAndValidateIsbn10(event, idValue) {
    // parsing valid ISBN that passes checks
    idValue = parseIsbn(idValue);
    if (!isFormatValidIsbn10(idValue)) {
        return displayIsbnError(event, invalidIsbn10);
    }
    if (!isChecksumValidIsbn10(idValue)) {
        return displayIsbnError(event, invalidChecksum);
    }
    document.getElementById('id_value').value = idValue;
}

function parseAndValidateIsbn13(event, idValue) {
    idValue = parseIsbn(idValue);
    if (!isFormatValidIsbn13(idValue)) {
        return displayIsbnError(event, invalidIsbn13);
    }
    if (!isChecksumValidIsbn13(idValue)) {
        return displayIsbnError(event, invalidChecksum);
    }
    document.getElementById('id_value').value = idValue;
}

function parseAndValidateLccn(event, idValue) {
    idValue = parseLccn(idValue);
    if (!isValidLccn(idValue)) {
        return displayLccnError(event, invalidLccn);
    }
    document.getElementById('id_value').value = idValue;
}

function autoCompleteIdName(){
    const idValue = document.querySelector('input#id_value').value.trim();
    const idValueIsbn = parseIsbn(idValue);
    const currentSelection = document.getElementById('id_name').value;

    if (isFormatValidIsbn10(idValueIsbn) && isChecksumValidIsbn10(idValueIsbn)){
        document.getElementById('id_name').value = 'isbn_10';
    }

    else if (isFormatValidIsbn13(idValueIsbn) && isChecksumValidIsbn13(idValueIsbn)){
        document.getElementById('id_name').value = 'isbn_13';
    }

    else if ((isValidLccn(parseLccn(idValue)))){
        document.getElementById('id_name').value = 'lccn';
    }

    else {
        document.getElementById('id_name').value = currentSelection || '';
    }
}

function validatePublishDate() {
    // validate publish-date to make sure the date is not in future
    // used in templates/books/add.html
    const publish_date = this.value;
    // if it doesn't have even three digits then it can't be a future date
    const tokens = /(\d{3,})/.exec(publish_date);
    const year = new Date().getFullYear();
    const isValidDate = tokens && tokens[1] && parseInt(tokens[1]) <= year + 1; // allow one year in future.

    const errorDiv = document.getElementById('publish-date-errors');

    if (!isValidDate) {
        errorDiv.classList.remove('hidden');
        errorDiv.textContent = i18nStrings['invalid_publish_date'];
    } else {
        errorDiv.classList.add('hidden');
    }
}
