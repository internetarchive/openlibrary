import {parseIsbn, isFormatValidIsbn10, isChecksumValidIsbn10, isFormatValidIsbn13, isChecksumValidIsbn13} from './edit.js'

let invalidChecksum;
let invalidIsbn10;
let invalidIsbn13;

export function initAddBookImport () {
    $('.list-books a').on('click', function() {
        var li = $(this).parents('li').first();
        $('input#work').val(`/works/${li.attr('id')}`);
        $('form#addbook').trigger('submit');
    });
    $('#bookAddCont').on('click', function() {
        $('input#work').val('none-of-these');
        $('form#addbook').trigger('submit');
    });

    const i18nStrings = JSON.parse(document.querySelector('#id-errors').dataset.i18n)
    invalidChecksum = i18nStrings.invalid_checksum
    invalidIsbn10 = i18nStrings.invalid_isbn10
    invalidIsbn13 = i18nStrings.invalid_isbn13

    $('#addbook').on('submit', parseAndValidateIsbn);
    $('#id_value').on('input', clearIsbnError);
    $('#id_name').on('change', clearIsbnError);
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

function clearIsbnError() {
    addBookWithIsbnErrors = false;
    const errorDiv = document.getElementById('id-errors');
    errorDiv.classList.add('hidden');
    const confirm = document.getElementById('confirm-add');
    confirm.classList.add('hidden');
}

function parseAndValidateIsbn(event) {
    const fieldName = document.getElementById('id_name').value;
    const isbn = parseIsbn(document.getElementById('id_value').value);
    if (fieldName === 'isbn_10') {
        if (!isFormatValidIsbn10(isbn)) {
            return displayIsbnError(event, invalidIsbn10);
        }
        if (!isChecksumValidIsbn10(isbn)) {
            return displayIsbnError(event, invalidChecksum);
        }
    }
    else if (fieldName === 'isbn_13') {
        if (!isFormatValidIsbn13(isbn)) {
            return displayIsbnError(event, invalidIsbn13);
        }
        if (!isChecksumValidIsbn13(isbn)) {
            return displayIsbnError(event, invalidChecksum);
        }
    }
    // parsing valid ISBN that passes checks
    document.getElementById('id_value').value = isbn;
}
