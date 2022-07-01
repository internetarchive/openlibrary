/* global render_language_field, render_work_autocomplete_item, render_language_autocomplete_item, render_work_field */
/* Globals are provided by the edit edition template */

/* global render_author, render_author_autocomplete_item */
/* Globals are provided by the author-autocomplete template */

function error(errordiv, input, message) {
    $(errordiv).show().html(message);
    $(input).trigger('focus');
    return false;
}

function update_len() {
    var len = $('#excerpts-excerpt').val().length;
    var color;
    if (len > 2000) {
        color = '#e44028';
    } else {
        color = 'gray';
    }
    $('#excerpts-excerpt-len').html(2000 - len).css('color', color);
}

/**
 * Gets length of 'textid' section and limit textid value length to input 'limit'
 *
 * @param {String} textid  text section id name
 * @param {Number} limit   character number limit
 * @return {boolean} is character number below or equal to limit
 */
function limitChars(textid, limit) {
    var text = $(`#${textid}`).val();
    var textlength = text.length;
    if (textlength > limit) {
        $(`#${textid}`).val(text.substr(0, limit));
        return false;
    } else {
        return true;
    }
}

/**
 * This is needed because jQuery has no forEach equivalent that works with jQuery elements instead of DOM elements
 * @param selector - css selector used by jQuery
 * @returns {*[]} - array of jQuery elements
 */
function getJqueryElements(selector){
    const queryResult = $(selector);
    const jQueryElementArray = [];
    for (let i = 0; i < queryResult.length; i++){
        jQueryElementArray.push(queryResult.eq(i))
    }
    return jQueryElementArray;
}

export function initRoleValidation() {
    const dataConfig = JSON.parse(document.querySelector('#roles').dataset.config);
    $('#roles').repeat({
        vars: {prefix: 'edition--'},
        validate: function (data) {
            if (data.role === '' || data.role === '---') {
                return error('#role-errors', '#select-role', dataConfig['Please select a role.']);
            }
            if (data.name === '') {
                return error('#role-errors', '#role-name', dataConfig['You need to give this ROLE a name.'].replace(/ROLE/, data.role));
            }
            $('#role-errors').hide();
            return true;
        }
    });
}

/**
 * isIsbnDedupe takes an isbn string and returns true if the given ISBN
 * is already added to this edition.
 * @param isbn - ISBN string duplication checking
 * @returns true if the given ISBN is already added to the edition
 */
function isIsbnDupe(isbn) {
    const isbnEntries = document.querySelectorAll('.isbn_10, .isbn_13');
    return Array.from(isbnEntries).some(entry => entry['value'] === isbn);
}

/**
 * isFormatValidIsbn10 takes an isbn string and verifies that is the
 * correct length and has the correct characters for an ISBN. It does
 * not verify the checksum.
 * @param isbn - string
 * returns - true if the isbn has a valid format, and false otherwise.
 */
function isFormatValidIsbn10(isbn) {
    const regex = /^[0-9]{9}[0-9X]$/;
    // Check ISBN format
    if (regex.test(isbn) === true) {
        return true;
    }
    return false
}

/**
 * isChecksumValidIsbn10 checks the format and validation for ISBN 10.
 * Adapted from https://www.oreilly.com/library/view/regular-expressions-cookbook/9781449327453/ch04s13.html
 * @param isbn - ISBN string for validating
 * @returns true if ISBN string is a valid ISBN 10
 */
export function isChecksumValidIsbn10(isbn) {
    const chars = isbn.split('');
    let last = chars.pop();
    let check;

    // With ISBN 10, the last character can be [0-9] or string 'X'.
    if (last !== 'X') {
        last = parseInt(last);
    }

    // Compute the ISBN-10 check digit
    chars.reverse();
    const sum = chars
        .map((char, idx) => ((idx + 2) * parseInt(char, 10)))
        .reduce((acc, sum) => acc + sum, 0)

    check = 11 - (sum % 11);
    if (check === 10) {
        check = 'X';
    } else if (check === 11) {
        check = 0;
    }

    if (check === last) {
        // Valid
        return true
    }

    return false
}

/**
 * isFormatValidIsbn13 takes an isbn string and verifies that is the
 * correct length and has the correct characters for an ISBN. It does
 * not verify the checksum.
 * @param isbn - string
 * returns - true if the isbn has a valid format, and false otherwise.
 */
function isFormatValidIsbn13(isbn) {
    const regex = /^[0-9]{13}$/
    if (regex.test(isbn) === true) {
        return true;
    }
    return false
}

/**
 * isChecksumValidIsbn13 checks the format and validation for ISBN 13.
 * Adapted from https://www.oreilly.com/library/view/regular-expressions-cookbook/9781449327453/ch04s13.html
 * @param isbn - ISBN string for validating
 * @returns true if ISBN string is a valid ISBN 13
 */
export function isChecksumValidIsbn13(isbn) {
    const chars = isbn.split('');
    // Remove the final ISBN digit from `chars`, and assign it to `last` for comparison.
    const last = parseInt(chars.pop());
    let check;

    const sum = chars
        .map((char, idx) => ((idx % 2 * 2 + 1) * parseInt(char, 10)))
        .reduce((sum, num) => sum + num, 0);

    check = 10 - (sum % 10);
    if (check === 10) {
        check = 0;
    }

    if (check === last) {
        // Valid
        return true
    }

    return false
}

/**
 * parseIsbn removes spaces and hyphens from an ISBN string and returns it.
 * @param isbn - ISBN string for parsing
 * @returns string - parsed isbn string
 */
function parseIsbn(isbn) {
    return isbn.replace(/[ -]/g, '');
}

/**
 * isbnConfirmAdd displays a confirmation box in the error div to confirm the
 * addition of an ISBN with a valid form but which fails the checksum.
 * The sessionStorage is read by js/jquery.repeat.js when a user confirms they
 * wish to add the ISBN.
 * @param data - data from the input form, gathered via js/jquery.repeat.js
 * @param isbnConfirmString - a const with the HTML to create the confirmation message/buttons
 */
export function isbnConfirmAdd(data, isbnConfirmString) {
    // Display the error and option to add the ISBN anyway.
    $('#id-errors').show().html(isbnConfirmString);
    // $('id-value').trigger('focus');
    // Handle clearing the error and removing sessionStorage as needed. Added ISBNs will have
    // the sessionStorage cleared in js/jquery.repeat.js once its read there.

    const yesButtonSelector = '#yes-add-isbn'
    const noButtonSelector = '#do-not-add-isbn'
    const onYes = () => {$('#id-errors').hide()};
    const onNo = () => {
        $('#id-errors').hide();
        sessionStorage.removeItem('data');
    }
    $(document).on('click', yesButtonSelector, onYes);
    $(document).on('click', noButtonSelector, onNo);

    // const yesButton = document.getElementById('yes-add-isbn')
    // const noButton = document.getElementById('do-not-add-isbn')
    // if (yesButton) {yesButton.addEventListener('click', () => {$('#id-errors').hide()})}
    // if (noButton) {noButton.addEventListener('click', () => {
    //     $('#id-errors').hide();
    //     sessionStorage.removeItem('data');
    // })}

    // Save the data to sessionStorage so it can be picked up via onAdd in js/jquery.repeat.js when
    // the user confirms adding the invalid ISBN.
    sessionStorage.setItem('data', JSON.stringify(data));
    return false;
}

/**
 * identifierValidationFunc is called by initIdentifierValidation(), along with
 * tests in tests/unit/js/editEditionsPage.test.js, to validate the addition
 * of new ISBNs to an edition.
 * @params data - data from the input form
 * @returns true/false - true if ISBN passes validation, and false otherwise.
 */
export function identifierValidationFunc(data) {
    const dataConfig = JSON.parse(document.querySelector('#identifiers').dataset.config);
    const isbnConfirmString = `ISBN ${data.value} may be invalid. Add it anyway? <button class="repeat-add" id="yes-add-isbn" type="button">Yes</button>&nbsp;<button id="do-not-add-isbn" type="button">No</button>`;

    // Ensure there is no stale session data.
    if (sessionStorage.getItem('data')) {sessionStorage.removeItem('data')}

    if (data.name === '' || data.name === '---') {
        return error('#id-errors', 'select-id', dataConfig['Please select an identifier.'])
    }
    const label = $('#select-id').find(`option[value='${data.name}']`).html();
    if (data.value === '') {
        return error('#id-errors', 'id-value', dataConfig['You need to give a value to ID.'].replace(/ID/, label));
    }
    if (['ocaid'].includes(data.name) && /\s/g.test(data.value)) {
        return error('#id-errors', 'id-value', dataConfig['ID ids cannot contain whitespace.'].replace(/ID/, label));
    }
    // Remove spaces and hyphens before checking ISBN 10.
    if (data.name === 'isbn_10') {
        data.value = parseIsbn(data.value);
    }
    if (data.name === 'isbn_10' && isFormatValidIsbn10(data.value) === false) {
        return error('#id-errors', 'id-value', dataConfig['ID must be exactly 10 characters [0-9] or X.'].replace(/ID/, label));
    }
    if (data.name === 'isbn_10' && isIsbnDupe(data.value) === true) {
        return error('#id-errors', 'id-value', dataConfig['That ISBN already exists for this edition.'].replace(/ISBN/, label));
    }
    // Remove spaces and hyphens before checking ISBN 13.
    if (data. name === 'isbn_13') {
        data.value = parseIsbn(data.value);
    }
    if (data.name === 'isbn_13' && isFormatValidIsbn13(data.value) === false) {
        return error('#id-errors', 'id-value', dataConfig['ID must be exactly 13 digits [0-9]. For example: 978-1-56619-909-4'].replace(/ID/, label));
    }
    if (data.name === 'isbn_13' && isIsbnDupe(data.value) === true) {
        return error('#id-errors', 'id-value', dataConfig['That ISBN already exists for this edition.'].replace(/ISBN/, label));
    }
    // Here the ISBN has a valid format, but also has an invalid checksum. Give the user a chance to verify
    // the ISBN, as books sometimes issue with invalid ISBNs and we want to be able to add them.
    // See https://en-academic.com/dic.nsf/enwiki/8948#cite_ref-18 for more.
    if (data.name === 'isbn_10' && isFormatValidIsbn10(data.value) === true && isChecksumValidIsbn10(data.value) === false) {

        isbnConfirmAdd(data, isbnConfirmString)
        return false
    }
    if (data.name === 'isbn_13' && isFormatValidIsbn13(data.value) === true && isChecksumValidIsbn13(data.value) === false) {

        isbnConfirmAdd(data, isbnConfirmString)
        return false
    }
    $('#id-errors').hide();
    return true;
}

export function initIdentifierValidation() {
    $('#identifiers').repeat({
        vars: {prefix: 'edition--'},
        validate: function(data) {return identifierValidationFunc(data)},
    });
}

export function initClassificationValidation() {
    const dataConfig = JSON.parse(document.querySelector('#classifications').dataset.config);
    $('#classifications').repeat({
        vars: {prefix: 'edition--'},
        validate: function (data) {
            if (data.name === '' || data.name === '---') {
                return error('#classification-errors', '#select-classification', dataConfig['Please select a classification.']);
            }
            if (data.value === '') {
                const label = $('#select-classification').find(`option[value='${data.name}']`).html();
                return error('#classification-errors', '#classification-value', dataConfig['You need to give a value to CLASS.'].replace(/CLASS/, label));
            }
            $('#classification-errors').hide();
            return true;
        }
    });
}

export function initLanguageMultiInputAutocomplete() {
    $(function() {
        getJqueryElements('.multi-input-autocomplete--language').forEach(jqueryElement => {
            jqueryElement.setup_multi_input_autocomplete(
                'input.language-autocomplete',
                render_language_field,
                {endpoint: '/languages/_autocomplete'},
                {
                    max: 6,
                    formatItem: render_language_autocomplete_item
                }
            );
        })
    });
}

export function initWorksMultiInputAutocomplete() {
    $(function() {
        getJqueryElements('.multi-input-autocomplete--works').forEach(jqueryElement => {
            /* Values in the html passed from Python code */
            const dataConfig = JSON.parse(jqueryElement[0].dataset.config);
            jqueryElement.setup_multi_input_autocomplete(
                'input.work-autocomplete',
                render_work_field,
                {
                    endpoint: '/works/_autocomplete',
                    addnew: dataConfig['isPrivilegedUser'] === 'true',
                    new_name: dataConfig['-- Move to a new work'],
                },
                {
                    minChars: 2,
                    max: 11,
                    matchSubset: false,
                    autoFill: false,
                    formatItem: render_work_autocomplete_item
                });
        });
    });
}

export function initAuthorMultiInputAutocomplete() {
    getJqueryElements('.multi-input-autocomplete--author').forEach(jqueryElement => {
        /* Values in the html passed from Python code */
        const dataConfig = JSON.parse(jqueryElement[0].dataset.config);
        jqueryElement.setup_multi_input_autocomplete(
            'input.author-autocomplete',
            render_author.bind(null, dataConfig.name_path, dataConfig.dict_path, false),
            {
                endpoint: '/authors/_autocomplete',
                // Don't render "Create new author" if searching by key
                addnew: query => !/OL\d+A/i.test(query),
            },
            {
                minChars: 2,
                max: 11,
                matchSubset: false,
                autoFill: false,
                formatItem: render_author_autocomplete_item
            });
    });
}

export function initEditRow(){
    document.querySelector('#add_row_button').addEventListener('click', ()=>add_row('website'));
}

/**
 * Adds another input box below the last when adding multiple websites to user profile.
 * @param string name - when prefixed with clone_ should match an element identifier in the page. e.g. if name would refer to clone_website
 **/
function add_row(name) {
    const inputBoxes = document.querySelectorAll(`#clone_${name} input`);
    const inputBox = document.createElement('input');
    inputBox.name = `${name}#${inputBoxes.length}`;
    inputBox.type = 'text';
    inputBoxes[inputBoxes.length-1].after(inputBox);
}

function show_hide_title() {
    if ($('#excerpts-display .repeat-item').length > 1) {
        $('#excerpts-so-far').show();
    } else {
        $('#excerpts-so-far').hide();
    }
}

export function initEditExcerpts() {
    $('#excerpts').repeat({
        vars: {
            prefix: 'work--excerpts',
        },
        validate: function(data) {
            if (!data.excerpt) {
                return error('#excerpts-errors', '#excerpts-excerpt', 'Please provide an excerpt.');
            }
            if (data.excerpt.length > 2000) {
                return error('#excerpts-errors', '#excerpts-excerpt', 'That excerpt is too long.')
            }
            $('#excerpts-errors').hide();
            return true;
        }
    });

    // update length on every keystroke
    $('#excerpts-excerpt').on('keyup', function() {
        limitChars('excerpts-excerpt', 2000);
        update_len();
    });

    // update length on add.
    $('#excerpts')
        .on('repeat-add', update_len)
        .on('repeat-add', show_hide_title)
        .on('repeat-remove', show_hide_title);

    // update length on load
    update_len();
    show_hide_title();
}

/**
 * Initializes links element on edit page.
 *
 * Assumes presence of elements with id:
 *    - '#links' and 'data-prefix' attribute
 *    - '#link-label'
 *    - '#link-url'
 *    - '#link-errors'
 */
export function initEditLinks() {
    $('#links').repeat({
        vars: {
            prefix: $('#links').data('prefix')
        },
        validate: function(data) {
            if (data.url.trim() === '' || data.url.trim() === 'https://') {
                $('#link-errors').html('Please provide a URL.');
                $('#link-errors').removeClass('hidden');
                $('#link-url').trigger('focus');
                return false;
            }
            if (data.title.trim() === '') {
                $('#link-errors').html('Please provide a label.');
                $('#link-errors').removeClass('hidden');
                $('#link-label').trigger('focus');
                return false;
            }
            $('#link-errors').addClass('hidden');
            return true;
        }
    });
}

/**
 * Initializes edit page.
 *
 * Assumes presence of elements with id:
 *    - '#link_edition'
 *    - '#tabsAddbook'
 *    - '#contentHead'
 */
export function initEdit() {
    var hash = document.location.hash || '#edition';
    var tab = hash.split('/')[0];
    var link = `#link_${tab.substring(1)}`;
    var fieldname = `:input${hash.replace('/', '-')}`;

    $(link).trigger('click');

    // input field is enabled only after the tab is selected and that takes some time after clicking the link.
    // wait for 1 sec after clicking the link and focus the input field
    if ($(fieldname).length !== 0) {
        setTimeout(function() {
            // scroll such that top of the content is visible
            $(fieldname).trigger('focus');
            $(window).scrollTop($('#contentHead').offset().top);
        }, 1000);
    }
}
