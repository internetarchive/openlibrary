import { isbnOverride } from './isbnOverride';
import {
    parseIsbn,
    parseLccn,
    isChecksumValidIsbn10,
    isChecksumValidIsbn13,
    isFormatValidIsbn10,
    isFormatValidIsbn13,
    isValidLccn,
    isIdDupe
} from './idValidation';
import { init as initAutocomplete } from './autocomplete';
import { init as initJqueryRepeat } from './jquery.repeat';

/* global render_seed_field, render_language_field, render_lazy_work_preview, render_language_autocomplete_item, render_work_field, render_work_autocomplete_item */
/* Globals are provided by the edit edition template */

/* global render_author, render_author_autocomplete_item */
/* Globals are provided by the author-autocomplete template */

/* global render_subject_autocomplete_item */
/* Globals are provided by the edit about template */

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
    initJqueryRepeat();
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
            $('#select-role, #role-name').val('');
            return true;
        }
    });
}

/**
 * Displays a confirmation box in the error div to confirm the addition of an
 * ISBN with a valid form but which fails the checksum.
 * @param {Object} data  data from the input form, gathered via js/jquery.repeat.js
 * @param {String} isbnConfirmString  a const with the HTML to create the confirmation message/buttons
 */
export function isbnConfirmAdd(data) {
    const isbnConfirmString = `ISBN ${data.value} may be invalid. Add it anyway? <button class="repeat-add" id="yes-add-isbn" type="button">Yes</button>&nbsp;<button id="do-not-add-isbn" type="button">No</button>`;
    // Display the error and option to add the ISBN anyway.
    $('#id-errors').show().html(isbnConfirmString);

    const yesButtonSelector = '#yes-add-isbn'
    const noButtonSelector = '#do-not-add-isbn'
    const onYes = () => {
        $('#id-errors').hide();
    };
    const onNo = () => {
        $('#id-errors').hide();
        isbnOverride.clear();
    }
    $(document).on('click', yesButtonSelector, onYes);
    $(document).on('click', noButtonSelector, onNo);

    // Save the data to isbnOverride so it can be picked up via onAdd in
    // js/jquery.repeat.js when the user confirms adding the invalid ISBN.
    isbnOverride.set(data)
    return false;
}

/**
 * Called by validateIdentifiers(), validates the addition of new
 * ISBN 10 to an edition.
 * @param {Object} data  data from the input form
 * @param {Object} dataConfig  object mapping error messages to their string values
 * @param {String} label  formatted value of the identifier type name (ISBN 10)
 * @returns {boolean}  true if ISBN passes validation, else returns false and displays appropriate error
 */
function validateIsbn10(data, dataConfig, label) {
    data.value = parseIsbn(data.value);

    if (!isFormatValidIsbn10(data.value)) {
        return error('#id-errors', '#id-value', dataConfig['ID must be exactly 10 characters [0-9] or X.'].replace(/ID/, label));
    }
    // Here the ISBN has a valid format, but also has an invalid checksum. Give the user a chance to verify
    // the ISBN, as books sometimes issue with invalid ISBNs and we want to be able to add them.
    // See https://en-academic.com/dic.nsf/enwiki/8948#cite_ref-18 for more.
    else if (isFormatValidIsbn10(data.value) === true && isChecksumValidIsbn10(data.value) === false) {
        isbnConfirmAdd(data)
        return false
    }
    return true;
}

/**
 * Called by validateIdentifiers(), validates the addition of new
 * ISBN 13 to an edition.
 * @param {Object} data  data from the input form
 * @param {Object} dataConfig  object mapping error messages to their string values
 * @param {String} label  formatted value of the identifier type name (ISBN 13)
 * @returns {boolean}  true if ISBN passes validation, else returns false and displays appropriate error
 */
function validateIsbn13(data, dataConfig, label) {
    data.value = parseIsbn(data.value);

    if (isFormatValidIsbn13(data.value) === false) {
        return error('#id-errors', '#id-value', dataConfig['ID must be exactly 13 digits [0-9]. For example: 978-1-56619-909-4'].replace(/ID/, label));
    }
    // Here the ISBN has a valid format, but also has an invalid checksum. Give the user a chance to verify
    // the ISBN, as books sometimes issue with invalid ISBNs and we want to be able to add them.
    // See https://en-academic.com/dic.nsf/enwiki/8948#cite_ref-18 for more.
    else if (isFormatValidIsbn13(data.value) === true && isChecksumValidIsbn13(data.value) === false) {
        isbnConfirmAdd(data)
        return false
    }
    return true;
}

/**
 * Called by validateIdentifiers(), validates the addition of new
 * LCCN to an edition.
 * @param {Object} data  data from the input form
 * @param {Object} dataConfig  object mapping error messages to their string values
 * @param {String} label  formatted value of the identifier type name (LCCN)
 * @returns {boolean}  true if LCCN passes validation, else returns false and displays appropriate error
 */
function validateLccn(data, dataConfig, label) {
    data.value = parseLccn(data.value);

    if (isValidLccn(data.value) === false) {
        $('#id-value').val(data.value);
        return error('#id-errors', '#id-value', dataConfig['Invalid ID format'].replace(/ID/, label));
    }
    return true;
}

/**
 * Called by initIdentifierValidation(), along with tests in
 * tests/unit/js/editEditionsPage.test.js, to validate the addition of new
 * identifiers (ISBN, LCCN) to an edition.
 * @param {Object} data  data from the input form
 * @returns {boolean}  true if identifier passes validation
 */
export function validateIdentifiers(data) {
    const dataConfig = JSON.parse(document.querySelector('#identifiers').dataset.config);

    if (data.name === '' || data.name === '---') {
        $('#id-value').val(data.value);
        return error('#id-errors', '#select-id', dataConfig['Please select an identifier.'])
    }
    const label = $('#select-id').find(`option[value='${data.name}']`).html();
    if (data.value === '') {
        return error('#id-errors', '#id-value', dataConfig['You need to give a value to ID.'].replace(/ID/, label));
    }
    if (['ocaid'].includes(data.name) && /\s/g.test(data.value)) {
        return error('#id-errors', '#id-value', dataConfig['ID ids cannot contain whitespace.'].replace(/ID/, label));
    }

    let validId = true;
    if (data.name === 'isbn_10') {
        validId = validateIsbn10(data, dataConfig, label);
    }
    else if (data.name === 'isbn_13') {
        validId = validateIsbn13(data, dataConfig, label);
    }
    else if (data.name === 'lccn') {
        validId = validateLccn(data, dataConfig, label);
    }

    // checking for duplicate identifier entry on all identifier types
    // expects parsed ids so placed after validate
    const entries = document.querySelectorAll(`.${data.name}`);
    if (isIdDupe(entries, data.value) === true) {
        // isbnOverride being set will override the dupe checker, so clear isbnOverride if there's a dupe.
        if (isbnOverride.get()) {isbnOverride.clear()}
        return error('#id-errors', '#id-value', dataConfig['That ID already exists for this edition.'].replace(/ID/, label));
    }

    if (validId === false) return false;
    $('#id-errors').hide();
    return true;
}

export function initClassificationValidation() {
    initJqueryRepeat();
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
            $('#select-classification, #classification-value').val('');
            return true;
        }
    });
}

export function initLanguageMultiInputAutocomplete() {
    initAutocomplete();
    $(function() {
        getJqueryElements('.multi-input-autocomplete--language').forEach(jqueryElement => {
            jqueryElement.setup_multi_input_autocomplete(
                render_language_field,
                {
                    endpoint: '/languages/_autocomplete',
                    sortable: true,
                },
                {
                    max: 6,
                    formatItem: render_language_autocomplete_item
                }
            );
        })
    });
}

export function initWorksMultiInputAutocomplete() {
    initAutocomplete();
    $(function() {
        getJqueryElements('.multi-input-autocomplete--works').forEach(jqueryElement => {
            /* Values in the html passed from Python code */
            const dataConfig = JSON.parse(jqueryElement[0].dataset.config || '{}');
            jqueryElement.setup_multi_input_autocomplete(
                render_work_field,
                {
                    endpoint: '/works/_autocomplete',
                    addnew: dataConfig['addnew'] || false,
                    new_name: dataConfig['new_name'] || '',
                    allow_empty: dataConfig['allow_empty'] || false,
                },
                {
                    minChars: 2,
                    max: 11,
                    matchSubset: false,
                    autoFill: true,
                    formatItem: render_work_autocomplete_item,
                });
        });
    });

    // Show the new work options checkboxes only if "New work" selected
    $('input[name="works--0"]').on('autocompleteselect', function(_event, ui) {
        $('.new-work-options').toggle(ui.item.key === '__new__');
    });
}

export function initSeedsMultiInputAutocomplete() {
    initAutocomplete();
    $(function() {
        getJqueryElements('.multi-input-autocomplete--seeds').forEach(jqueryElement => {
            /* Values in the html passed from Python code */
            jqueryElement.setup_multi_input_autocomplete(
                render_seed_field,
                {
                    endpoint: '/works/_autocomplete',
                    addnew: false,
                    allow_empty: true,
                    sortable: true,
                },
                {
                    minChars: 2,
                    max: 11,
                    matchSubset: false,
                    autoFill: true,
                    formatItem: render_lazy_work_preview,
                });
        });
    });
}

export function initAuthorMultiInputAutocomplete() {
    initAutocomplete();
    getJqueryElements('.multi-input-autocomplete--author').forEach(jqueryElement => {
        /* Values in the html passed from Python code */
        const dataConfig = JSON.parse(jqueryElement[0].dataset.config);
        jqueryElement.setup_multi_input_autocomplete(
            render_author.bind(null, dataConfig.name_path, dataConfig.dict_path, false),
            {
                endpoint: '/authors/_autocomplete',
                // Don't render "Create new author" if searching by key
                addnew: query => !/OL\d+A/i.test(query),
                sortable: true,
            },
            {
                minChars: 2,
                max: 11,
                matchSubset: false,
                autoFill: true,
                formatItem: render_author_autocomplete_item
            });
    });
}

export function initSubjectsAutocomplete() {
    initAutocomplete();
    getJqueryElements('.csv-autocomplete--subjects').forEach(jqueryElement => {
        const dataConfig = JSON.parse(jqueryElement[0].dataset.config);
        jqueryElement.setup_csv_autocomplete(
            'textarea',
            {
                endpoint: `/subjects_autocomplete?type=${dataConfig.facet}`,
                addnew: false,
            },
            {
                formatItem: render_subject_autocomplete_item,
            }
        );
    });

    /* Resize textarea to fit on input */
    $('.csv-autocomplete--subjects textarea').on('input', function () {
        this.style.height = 'auto';
        this.style.height = `${this.scrollHeight + 5}px`;
    });
}

export function initEditRow(){
    document.querySelector('#add_row_button').addEventListener('click', ()=>add_row('website'));
}

/**
 * Adds another input box below the last when adding multiple websites to user profile.
 * @param string name - when prefixed with clone_ should match an element identifier in the page. e.g. if name would refer to clone_website
 */
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
    initJqueryRepeat();
    $('#excerpts').repeat({
        vars: {
            prefix: 'work--excerpts',
        },
        validate: function(data) {
            const i18nStrings = JSON.parse(document.querySelector('#excerpts-errors').dataset.i18n);

            if (!data.excerpt) {
                return error('#excerpts-errors', '#excerpts-excerpt', i18nStrings['empty_excerpt']);
            }
            if (data.excerpt.length > 2000) {
                return error('#excerpts-errors', '#excerpts-excerpt', i18nStrings['over_wordcount']);
            }
            $('#excerpts-errors').hide();
            $('#excerpts-excerpt').val('');
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
    initJqueryRepeat();
    $('#links').repeat({
        vars: {
            prefix: $('#links').data('prefix')
        },
        validate: function(data) {
            const i18nStrings = JSON.parse(document.querySelector('#link-errors').dataset.i18n);
            const url = data.url.trim();

            if (data.title.trim() === '') {
                $('#link-errors').html(i18nStrings['empty_label']);
                $('#link-errors').removeClass('hidden');
                $('#link-label').trigger('focus');
                return false;
            }
            if (url === '') {
                $('#link-errors').html(i18nStrings['empty_url']);
                $('#link-errors').removeClass('hidden');
                $('#link-url').trigger('focus');
                return false;
            }
            if (!isValidURL(url)) {
                $('#link-errors').html(i18nStrings['invalid_url']);
                $('#link-errors').removeClass('hidden');
                $('#link-url').trigger('focus');
                return false;
            }
            $('#link-errors').addClass('hidden');
            $('#link-label, #link-url').val('');
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

/**
 * Assesses URL validity using built-in URL object.
 * @param string url
 */
function isValidURL(url) {
    try {
        new URL(url);
        return true;
    } catch (e) {
        return false;
    }
}
