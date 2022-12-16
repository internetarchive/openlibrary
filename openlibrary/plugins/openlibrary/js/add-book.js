import {parseIsbn, isFormatValidIsbn10, isChecksumValidIsbn10, isFormatValidIsbn13, isChecksumValidIsbn13} from './edit.js'

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
    $('#addbook').on('submit', parseAndValidateIsbn);
    $('#id_value').on('input', clearIsbnError);
    $('#id_name').on('change', clearIsbnError);
}

const isbn_invalid_checksum = 'Invalid ISBN checksum digit';
const isbn10_wrong_length_or_chars = 'ID must be exactly 10 characters [0-9 or X]. For example 0-19-853453-1 or 0198534531';
const isbn13_wrong_length_or_chars = 'ID must be exactly 13 characters [0-9]. For example 978-3-16-148410-0 or 9783161484100';

// a flag to make raiseIsbnError perform differently upon subsequent calls
let addBookWithIsbnErrors = false;

function raiseIsbnError(event, errorMessage) {
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
            return raiseIsbnError(event, isbn10_wrong_length_or_chars);
        }
        if (!isChecksumValidIsbn10(isbn)) {
            return raiseIsbnError(event, isbn_invalid_checksum);
        }
    }
    else if (fieldName === 'isbn_13') {
        if (!isFormatValidIsbn13(isbn)) {
            return raiseIsbnError(event, isbn13_wrong_length_or_chars);
        }
        if (!isChecksumValidIsbn13(isbn)) {
            return raiseIsbnError(event, isbn_invalid_checksum);
        }
    }
    // parsing valid ISBN that passes checks
    document.getElementById('id_value').value = isbn;
}
