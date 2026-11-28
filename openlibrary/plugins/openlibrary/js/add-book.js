import {
    parseIsbn,
    parseLccn,
    parseOclc,
    isChecksumValidIsbn10,
    isChecksumValidIsbn13,
    isFormatValidIsbn10,
    isFormatValidIsbn13,
    isValidLccn,
    isValidOclc
} from './idValidation.js';
import { _ } from './i18n.js';
import { trimInputValues } from './utils.js';
import { isValidURL } from './edit.js';

export function initAddBookImport() {
    const addBookForm = document.querySelector('form#addbook');

    // getResponse() is missing until api.js finishes loading, and throws if the widget never rendered.
    function captchaSolved() {
        try {
            return Boolean(window.grecaptcha?.getResponse?.());
        } catch {
            return false;
        }
    }

    // On the matches page, picking a book posts the form, so hold it until the captcha is solved.
    function submitMatchChoice(work) {
        const needed = document.getElementById('recaptcha-needed');
        if (needed && !captchaSolved()) {
            needed.hidden = false;
            addBookForm.scrollIntoView({ behavior: 'smooth', block: 'center' });
            return;
        }
        document.querySelector('input#work').value = work;
        addBookForm.requestSubmit();
    }

    for (const link of document.querySelectorAll('.list-books a')) {
        link.addEventListener('click', function () {
            submitMatchChoice(`/works/${this.closest('li').id}`);
        });
    }
    document.getElementById('bookAddCont')?.addEventListener('click', function () {
        submitMatchChoice('none-of-these');
    });

    // The ID and publish-date fields are only rendered on add.html's form. check.html reuses the same #addbook/form[name=edit] markup
    // for its "possible matches" page, but has none of the fields this block wires up.
    if (document.getElementById('id_value')) {
        document.getElementById('id_value').addEventListener('change', autoCompleteIdName);
        document.getElementById('addbook').addEventListener('submit', parseAndValidateId);
        document.getElementById('id_value').addEventListener('input', clearErrors);
        document.getElementById('id_name').addEventListener('change', clearErrors);

        document.getElementById('publish_date').addEventListener('blur', validatePublishDate);

        // The Book URL field is only rendered for librarians
        const webBookUrl = document.getElementById('web_book_url');
        if (webBookUrl) {
            webBookUrl.addEventListener('blur', validateWebBookUrl);
            addBookForm.addEventListener('submit', validateWebBookUrl);
        }

        trimInputValues('input');

        // Prevents submission if the publish date is > 1 year in the future
        addBookForm.addEventListener('submit', function (event) {
            if (!document.getElementById('publish-date-errors').classList.contains('hidden')) {
                event.preventDefault();
            }
        });
    }
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
        isbnInput.focus({ focusVisible: true });
        event.preventDefault();
        return;
    }
    // parsing potentially invalid ISBN
    document.getElementById('id_value').value = parseIsbn(document.getElementById('id_value').value);
}

function displayIdentifierError(event, errorMessage) {
    const errorDiv = document.getElementById('id-errors');
    errorDiv.classList.remove('hidden');
    errorDiv.textContent = errorMessage;
    event.preventDefault();
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
    } else if (fieldName === 'isbn_13') {
        parseAndValidateIsbn13(event, idValue);
    } else if (fieldName === 'lccn') {
        parseAndValidateLccn(event, idValue);
    } else if (fieldName === 'oclc_numbers') {
        parseAndValidateOclc(event, idValue);
    } else if (!fieldName || !isEmptyId(event, idValue)) {
        document.getElementById('id_value').value = idValue.trim();
    }
}

function isEmptyId(event, idValue) {
    if (!idValue.trim()) {
        const errorDiv = document.getElementById('id-errors');
        errorDiv.classList.remove('hidden');
        errorDiv.textContent = _('Please enter a value for the selected identifier');
        event.preventDefault();
        return true;
    }
    return false;
}

function parseAndValidateIsbn10(event, idValue) {
    // parsing valid ISBN that passes checks
    idValue = parseIsbn(idValue);
    if (!isFormatValidIsbn10(idValue)) {
        return displayIsbnError(event, _('ID must be exactly 10 characters [0-9 or X]. For example 0-19-853453-1 or 0198534531'));
    }
    if (!isChecksumValidIsbn10(idValue)) {
        return displayIsbnError(event, _('Invalid ISBN checksum digit'));
    }
    document.getElementById('id_value').value = idValue;
}

function parseAndValidateIsbn13(event, idValue) {
    idValue = parseIsbn(idValue);
    if (!isFormatValidIsbn13(idValue)) {
        return displayIsbnError(event, _('ID must be exactly 13 characters [0-9]. For example 978-3-16-148410-0 or 9783161484100'));
    }
    if (!isChecksumValidIsbn13(idValue)) {
        return displayIsbnError(event, _('Invalid ISBN checksum digit'));
    }
    document.getElementById('id_value').value = idValue;
}

function parseAndValidateLccn(event, idValue) {
    idValue = parseLccn(idValue);
    if (!isValidLccn(idValue)) {
        return displayIdentifierError(event, _('Invalid LC Control Number format'));
    }
    document.getElementById('id_value').value = idValue;
}

function parseAndValidateOclc(event, idValue) {
    idValue = parseOclc(idValue);
    if (!isValidOclc(idValue)) {
        return displayIdentifierError(event, _('Invalid OCLC/WorldCat Control Number format'));
    }
    document.getElementById('id_value').value = idValue;
}

function autoCompleteIdName() {
    const idValue = document.querySelector('input#id_value').value.trim();
    const idValueIsbn = parseIsbn(idValue);
    const currentSelection = document.getElementById('id_name').value;

    if (isFormatValidIsbn10(idValueIsbn) && isChecksumValidIsbn10(idValueIsbn)) {
        document.getElementById('id_name').value = 'isbn_10';
    } else if (isFormatValidIsbn13(idValueIsbn) && isChecksumValidIsbn13(idValueIsbn)) {
        document.getElementById('id_name').value = 'isbn_13';
    } else if (isValidLccn(parseLccn(idValue))) {
        document.getElementById('id_name').value = 'lccn';
    } else {
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
    const isValidDate = tokens && tokens[1] && parseInt(tokens[1], 10) <= year + 1; // allow one year in future.

    const errorDiv = document.getElementById('publish-date-errors');

    if (!isValidDate) {
        errorDiv.classList.remove('hidden');
        errorDiv.textContent = _("Are you sure that's the published date?");
    } else {
        errorDiv.classList.add('hidden');
    }
}

export function isValidWebBookUrl(value) {
    const trimmed = value.trim();
    if (!trimmed) {
        return true;
    }
    return isValidURL(trimmed) && ['http:', 'https:'].includes(new URL(trimmed).protocol);
}

function validateWebBookUrl(event) {
    const input = document.getElementById('web_book_url');
    const errorDiv = document.getElementById('web-book-url-errors');

    if (isValidWebBookUrl(input.value)) {
        errorDiv.classList.add('hidden');
    } else {
        errorDiv.classList.remove('hidden');
        errorDiv.textContent = _('Please enter a valid URL starting with http:// or https://');
        event?.preventDefault();
    }
}
